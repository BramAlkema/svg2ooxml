"""Asset registration, media indexing, and filter asset management.

Extracted from DrawingMLWriter to keep the orchestrator focused on rendering
coordination.  All methods are pure moves — no behavioral changes.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from io import BytesIO
from typing import TYPE_CHECKING

from svg2ooxml.drawingml.assets import AssetRegistry
from svg2ooxml.drawingml.filter_fallback import resolve_filter_fallback_bounds
from svg2ooxml.drawingml.generator import px_to_emu
from svg2ooxml.io.emf import EMFRelationshipManager
from svg2ooxml.ir.scene import Group, Image

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.services.image_service import ImageService

logger = logging.getLogger(__name__)


class AssetPipeline:
    """Manages media registration, filter assets, and rasterised-group emission."""

    def __init__(self, *, image_service: ImageService | None = None) -> None:
        self._image_service = image_service
        self._emf_manager = EMFRelationshipManager()
        self._next_media_index = 1
        self._pattern_tile_media_cache: dict[tuple[str, str], str] = {}
        self._seen_filter_relationships: set[str] = set()
        # Set during each render via reset()
        self._assets: AssetRegistry | None = None
        self._trace_writer: Callable[..., None] | None = None
        self._scene_background_color: str | None = None

    def set_image_service(self, image_service: ImageService | None) -> None:
        """Update the image service used for on-the-fly media resolution."""
        self._image_service = image_service

    def reset(
        self,
        *,
        assets: AssetRegistry,
        trace_writer: Callable[..., None],
        scene_background_color: str | None = None,
    ) -> None:
        """Prepare for a new render pass."""
        self._assets = assets
        self._trace_writer = trace_writer
        self._scene_background_color = scene_background_color
        self._next_media_index = 1
        self._pattern_tile_media_cache.clear()
        self._seen_filter_relationships.clear()
        self._emf_manager.reset()

    def clear(self) -> None:
        """Release per-render references."""
        self._assets = None
        self._trace_writer = None

    @property
    def _current_assets(self) -> AssetRegistry:
        if self._assets is None:
            raise RuntimeError("Asset pipeline not initialised for current rendering run.")
        return self._assets

    def _trace(
        self,
        action: str,
        *,
        metadata: dict[str, object] | None = None,
        stage: str = "media",
    ) -> None:
        if self._trace_writer is not None:
            self._trace_writer(action, metadata=metadata, stage=stage)

    # ------------------------------------------------------------------
    # Media registration
    # ------------------------------------------------------------------

    def register_media(self, image: Image) -> str:
        ext = image.format.lower()
        if ext == "emf":
            if not isinstance(image.data, (bytes, bytearray)):
                raise TypeError("EMF images require inline byte data")
            metadata = image.metadata if isinstance(image.metadata, dict) else {}
            emf_meta = metadata.get("emf_asset") if isinstance(metadata, dict) else None
            preferred_id = None
            width_emu = None
            height_emu = None
            if isinstance(emf_meta, dict):
                preferred_id = emf_meta.get("relationship_id")
                width_emu = self._maybe_int(emf_meta.get("width_emu"))
                height_emu = self._maybe_int(emf_meta.get("height_emu"))
            entry, is_new = self._emf_manager.register(
                bytes(image.data),
                rel_id=preferred_id,
                width_emu=width_emu,
                height_emu=height_emu,
            )
            if is_new:
                self._current_assets.add_media(
                    relationship_id=entry.relationship_id,
                    filename=entry.filename,
                    data=entry.data,
                    content_type="image/x-emf",
                    width_emu=entry.width_emu,
                    height_emu=entry.height_emu,
                    source="emf",
                )
            if isinstance(emf_meta, dict):
                emf_meta["relationship_id"] = entry.relationship_id
                if entry.width_emu is not None:
                    emf_meta["width_emu"] = entry.width_emu
                if entry.height_emu is not None:
                    emf_meta["height_emu"] = entry.height_emu
            self._trace(
                "media_registered",
                metadata={
                    "format": "emf",
                    "relationship_id": entry.relationship_id,
                    "new_asset": is_new,
                    "width_emu": entry.width_emu,
                    "height_emu": entry.height_emu,
                    "image_source": metadata.get("image_source"),
                },
            )
            return entry.relationship_id

        r_id = f"rIdMedia{self._next_media_index}"
        filename = f"image{self._next_media_index}.{ext}"
        content_type = self._content_type_for_format(ext)
        self._next_media_index += 1

        data = image.data
        if data is None and image.href and self._image_service is not None:
            resource = self._image_service.resolve(image.href)
            if resource is not None:
                data = resource.data

        if data is None:
            logger.warning("Image data missing for %s; skipping media registration", image.href or "unknown")
            return ""

        data_bytes = data if isinstance(data, (bytes, bytearray)) else bytes(data)
        metadata = image.metadata if isinstance(image.metadata, dict) else {}
        if metadata.get("image_source") == "pattern_tile":
            digest = hashlib.md5(data_bytes, usedforsecurity=False).hexdigest()
            cache_key = (content_type, digest)
            existing_rel_id = self._pattern_tile_media_cache.get(cache_key)
            if existing_rel_id:
                self._trace(
                    "media_registered",
                    metadata={
                        "format": ext,
                        "relationship_id": existing_rel_id,
                        "width_px": getattr(image.size, "width", None),
                        "height_px": getattr(image.size, "height", None),
                        "image_source": metadata.get("image_source"),
                        "data_bytes": len(data_bytes),
                        "new_asset": False,
                    },
                )
                return existing_rel_id

            self._pattern_tile_media_cache[cache_key] = r_id

        self._current_assets.add_media(
            relationship_id=r_id,
            filename=filename,
            data=data_bytes,
            content_type=content_type,
            source="image",
        )
        self._trace(
            "media_registered",
            metadata={
                "format": ext,
                "relationship_id": r_id,
                "width_px": getattr(image.size, "width", None),
                "height_px": getattr(image.size, "height", None),
                "image_source": metadata.get("image_source"),
                "data_bytes": len(data_bytes),
                "new_asset": True,
            },
        )
        return r_id

    # ------------------------------------------------------------------
    # Filter assets
    # ------------------------------------------------------------------

    def register_filter_assets(self, metadata: dict[str, object] | None) -> None:
        if not isinstance(metadata, dict):
            return
        policy = metadata.get("policy")
        if not isinstance(policy, dict):
            return
        media_policy = policy.get("media")
        if not isinstance(media_policy, dict):
            return
        filter_assets = media_policy.get("filter_assets")
        if not isinstance(filter_assets, dict):
            return

        for assets in filter_assets.values():
            if not isinstance(assets, list):
                continue
            for asset in assets:
                if not isinstance(asset, dict):
                    continue
                data_hex = asset.get("data_hex")
                raw_data = asset.get("data")
                if not isinstance(data_hex, str) or not data_hex:
                    if isinstance(raw_data, (bytes, bytearray)):
                        binary = bytes(raw_data)
                    else:
                        continue
                else:
                    binary = bytes.fromhex(data_hex)

                asset_type = asset.get("type")
                if asset_type == "emf":
                    preferred_id = asset.get("relationship_id")
                    if not isinstance(preferred_id, str) or not preferred_id:
                        preferred_id = None
                    width_emu = self._maybe_int(asset.get("width_emu"))
                    height_emu = self._maybe_int(asset.get("height_emu"))
                    entry, is_new = self._emf_manager.register(
                        binary,
                        rel_id=preferred_id,
                        width_emu=width_emu,
                        height_emu=height_emu,
                    )
                    if preferred_id is None:
                        asset["relationship_id"] = entry.relationship_id
                        preferred_id = entry.relationship_id
                    if entry.width_emu is not None:
                        asset["width_emu"] = entry.width_emu
                    if entry.height_emu is not None:
                        asset["height_emu"] = entry.height_emu
                    rel_id = preferred_id or entry.relationship_id
                    if rel_id in self._seen_filter_relationships:
                        continue
                    self._current_assets.add_media(
                        relationship_id=rel_id,
                        filename=entry.filename,
                        data=entry.data,
                        content_type="image/x-emf",
                        width_emu=entry.width_emu,
                        height_emu=entry.height_emu,
                        source="filter",
                    )
                    self._trace(
                        "filter_asset_registered",
                        stage="filter",
                        metadata={
                            "format": "emf",
                            "relationship_id": rel_id,
                            "width_emu": entry.width_emu,
                            "height_emu": entry.height_emu,
                        },
                    )
                    self._seen_filter_relationships.add(rel_id)
                    continue

                ext = "png"
                content_type = "image/png"
                rel_id = asset.get("relationship_id")
                if not isinstance(rel_id, str) or not rel_id:
                    rel_id = f"rId{self._next_media_index}"
                    asset["relationship_id"] = rel_id
                if rel_id in self._seen_filter_relationships:
                    continue
                if self._should_flatten_filter_png_for_powerpoint(asset):
                    binary = self._flatten_filter_png_for_powerpoint(binary)
                filename = f"media_{self._next_media_index}.{ext}"
                self._next_media_index += 1
                self._current_assets.add_media(
                    relationship_id=rel_id,
                    filename=filename,
                    data=binary,
                    content_type=content_type,
                    source="filter",
                )
                self._trace(
                    "filter_asset_registered",
                    stage="filter",
                    metadata={
                        "format": content_type,
                        "relationship_id": rel_id,
                    },
                )
                self._seen_filter_relationships.add(rel_id)

    @staticmethod
    def _should_flatten_filter_png_for_powerpoint(asset: dict[str, object]) -> bool:
        if bool(asset.get("flatten_for_powerpoint")):
            return True
        metadata = asset.get("metadata")
        return isinstance(metadata, dict) and bool(metadata.get("flatten_for_powerpoint"))

    def _flatten_filter_png_for_powerpoint(self, data: bytes) -> bytes:
        background = (self._scene_background_color or "FFFFFF").lstrip("#").upper()
        if len(background) != 6:
            background = "FFFFFF"
        try:
            from PIL import Image

            image = Image.open(BytesIO(data)).convert("RGBA")
        except Exception:
            return data

        alpha = image.getchannel("A")
        if alpha.getextrema() == (255, 255):
            return data

        try:
            bg_rgb = tuple(int(background[index:index + 2], 16) for index in (0, 2, 4))
        except ValueError:
            bg_rgb = (255, 255, 255)

        flattened = Image.new("RGBA", image.size, bg_rgb + (255,))
        flattened.alpha_composite(image)
        buffer = BytesIO()
        flattened.save(buffer, format="PNG")
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # Filter fallback rendering
    # ------------------------------------------------------------------

    def render_group_filter_fallback(
        self,
        group: Group,
        shape_id: int,
        metadata: dict[str, object],
    ) -> str | None:
        policy = metadata.get("policy")
        if not isinstance(policy, dict):
            return None
        media_policy = policy.get("media")
        if not isinstance(media_policy, dict):
            return None
        filter_assets = media_policy.get("filter_assets")
        if not isinstance(filter_assets, dict):
            return None
        filters = metadata.get("filters")
        if not isinstance(filters, list):
            return None
        filter_meta = metadata.get("filter_metadata")
        if not isinstance(filter_meta, dict):
            filter_meta = {}

        for entry in filters:
            if not isinstance(entry, dict):
                continue
            filter_id = entry.get("id")
            if not isinstance(filter_id, str) or not filter_id:
                continue
            fallback = entry.get("fallback")
            fallback = fallback.lower() if isinstance(fallback, str) else None
            if fallback not in {"bitmap", "raster", "emf", "vector"}:
                continue
            assets = filter_assets.get(filter_id)
            if not isinstance(assets, list):
                continue
            asset_type = "emf" if fallback in {"emf", "vector"} else "raster"
            asset = next(
                (
                    item
                    for item in assets
                    if isinstance(item, dict)
                    and item.get("type") == asset_type
                    and isinstance(item.get("relationship_id"), str)
                ),
                None,
            )
            if asset is None:
                continue
            rel_id = asset["relationship_id"]
            meta = filter_meta.get(filter_id)
            bounds = resolve_filter_fallback_bounds(
                group.bbox,
                meta if isinstance(meta, dict) else None,
            )
            if bounds is None:
                continue
            if bounds.width <= 0 or bounds.height <= 0:
                continue
            return (
                f'<p:pic>'
                f'<p:nvPicPr>'
                f'<p:cNvPr id="{shape_id}" name="Picture {shape_id}"/>'
                f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
                f'<p:nvPr/>'
                f'</p:nvPicPr>'
                f'<p:blipFill>'
                f'<a:blip r:embed="{rel_id}"/>'
                f'<a:stretch><a:fillRect/></a:stretch>'
                f'</p:blipFill>'
                f'<p:spPr>'
                f'<a:xfrm>'
                f'<a:off x="{px_to_emu(bounds.x)}" y="{px_to_emu(bounds.y)}"/>'
                f'<a:ext cx="{px_to_emu(bounds.width)}" cy="{px_to_emu(bounds.height)}"/>'
                f'</a:xfrm>'
                f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
                f'</p:spPr>'
                f'</p:pic>'
            )
        return None

    # ------------------------------------------------------------------
    # Rasterised group emission
    # ------------------------------------------------------------------

    def emit_raster_group(self, raster, group, shape_id, metadata) -> str | None:
        """Emit a rasterized group as an image shape with alpha."""
        rid = f"rId{self._next_media_index}"
        filename = f"image{self._next_media_index}.png"
        self._next_media_index += 1
        self._current_assets.add_media(
            relationship_id=rid,
            filename=filename,
            data=raster.data,
            content_type="image/png",
            source="rasterized_group",
        )

        bounds = raster.bounds
        alpha_ppt = int(round(group.opacity * 100000))
        alpha_attr = f'<a:alphaModFix amt="{alpha_ppt}"/>' if alpha_ppt < 100000 else ""

        return (
            f'<p:pic>'
            f'<p:nvPicPr>'
            f'<p:cNvPr id="{shape_id}" name="Group {shape_id}"/>'
            f'<p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
            f'<p:nvPr/>'
            f'</p:nvPicPr>'
            f'<p:blipFill>'
            f'<a:blip r:embed="{rid}">{alpha_attr}</a:blip>'
            f'<a:stretch><a:fillRect/></a:stretch>'
            f'</p:blipFill>'
            f'<p:spPr>'
            f'<a:xfrm>'
            f'<a:off x="{px_to_emu(bounds.x)}" y="{px_to_emu(bounds.y)}"/>'
            f'<a:ext cx="{px_to_emu(bounds.width)}" cy="{px_to_emu(bounds.height)}"/>'
            f'</a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
            f'</p:spPr>'
            f'</p:pic>'
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _content_type_for_format(ext: str) -> str:
        mapping = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "svg": "image/svg+xml",
            "emf": "image/x-emf",
        }
        return mapping.get(ext, "application/octet-stream")

    @staticmethod
    def _maybe_int(value: object) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None
