"""DrawingML writer that renders IR scenes to slide XML fragments."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from svg2ooxml.core.ir import IRScene
from svg2ooxml.io.emf import EMFRelationshipManager
from svg2ooxml.ir.scene import Group, Image, SceneGraph
from svg2ooxml.ir.text import TextFrame

from .animation_pipeline import AnimationPipeline
from .assets import AssetRegistry
from .clipmask import clip_xml_for
from .generator import EMU_PER_PX, DrawingMLPathGenerator, px_to_emu
from .mask_pipeline import MaskPipeline
from .navigation import register_navigation
from .rasterizer import SKIA_AVAILABLE, Rasterizer
from .result import DrawingMLRenderResult
from .shape_renderer import DrawingMLShapeRenderer
from .text_renderer import DrawingMLTextRenderer

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.tracing import ConversionTracer
    from svg2ooxml.services.image_service import ImageService

DEFAULT_SLIDE_SIZE = (9144000, 6858000)  # 10" x 7.5"

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _assets_root() -> Path:
    return _project_root() / "assets" / "pptx_templates"


def _apply_mask_alpha(element, alpha: float):
    """Multiply mask alpha into an element's fill and stroke paint opacities.

    Used for uniform-opacity masks where the mask is equivalent to reducing
    the element's overall alpha.  This avoids complex mask geometry and matches
    PowerPoint's "Convert to Shape" behavior for simple opacity masks.
    """
    from svg2ooxml.ir.paint import (
        GradientStop,
        LinearGradientPaint,
        RadialGradientPaint,
        SolidPaint,
    )

    def _scale_stops(stops, a: float):
        return [
            GradientStop(offset=s.offset, rgb=s.rgb, opacity=s.opacity * a)
            for s in stops
        ]

    fill = getattr(element, "fill", None)
    new_fill = fill
    if isinstance(fill, SolidPaint):
        new_fill = replace(fill, opacity=fill.opacity * alpha)
    elif isinstance(fill, (LinearGradientPaint, RadialGradientPaint)):
        new_fill = replace(fill, stops=_scale_stops(fill.stops, alpha))

    stroke = getattr(element, "stroke", None)
    new_stroke = stroke
    if stroke is not None:
        paint = getattr(stroke, "paint", None)
        if isinstance(paint, SolidPaint):
            new_stroke = replace(stroke, paint=replace(paint, opacity=paint.opacity * alpha))
        elif isinstance(paint, (LinearGradientPaint, RadialGradientPaint)):
            new_stroke = replace(stroke, paint=replace(paint, stops=_scale_stops(paint.stops, alpha)))

    try:
        element = replace(element, fill=new_fill, stroke=new_stroke, mask=None, mask_instance=None)
    except TypeError:
        # Element may not have all fields; try partial replacement.
        try:
            element = replace(element, fill=new_fill, stroke=new_stroke)
        except TypeError:
            pass
    return element


class DrawingMLWriter:
    """Render IR scene graphs into DrawingML shape fragments."""

    def __init__(self, *, template_dir: Path | None = None, image_service: ImageService | None = None) -> None:
        self._template_dir = template_dir or _assets_root()
        self._image_service = image_service
        self._slide_template = (self._template_dir / "slide_template.xml").read_text(encoding="utf-8")
        self._text_template = (self._template_dir / "text_shape_template.xml").read_text(encoding="utf-8")
        self._rectangle_template = (self._template_dir / "shape_rectangle.xml").read_text(encoding="utf-8")
        self._preset_template = (self._template_dir / "shape_preset.xml").read_text(encoding="utf-8")
        self._path_template = (self._template_dir / "shape_path.xml").read_text(encoding="utf-8")
        self._line_template = (self._template_dir / "shape_line.xml").read_text(encoding="utf-8")
        self._picture_template = (self._template_dir / "picture_shape.xml").read_text(encoding="utf-8")
        self._wordart_template = (self._template_dir / "wordart_shape_template.xml").read_text(encoding="utf-8")
        self._path_generator = DrawingMLPathGenerator()
        self._emf_manager = EMFRelationshipManager()
        self._asset_registry: AssetRegistry | None = None
        self._next_media_index = 1
        self._next_navigation_index = 1
        self._seen_filter_relationships: set[str] = set()
        self._mask_pipeline = MaskPipeline()
        self._rasterizer: Rasterizer | None = None
        self._animation_pipeline = AnimationPipeline(trace_writer=self._trace_writer)
        self._text_renderer: DrawingMLTextRenderer | None = None
        self._shape_renderer: DrawingMLShapeRenderer | None = None
        if SKIA_AVAILABLE:  # pragma: no branch
            try:
                self._rasterizer = Rasterizer()
            except Exception:  # pragma: no cover - defensive
                self._rasterizer = None
        self._tracer: ConversionTracer | None = None

    @property
    def _assets(self) -> AssetRegistry:
        if self._asset_registry is None:
            raise RuntimeError("Asset registry not initialised for current rendering run.")
        return self._asset_registry

    def set_image_service(self, image_service: ImageService | None) -> None:
        """Update the image service used for on-the-fly media resolution."""
        self._image_service = image_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_scene(
        self,
        scene: SceneGraph,
        *,
        slide_size: tuple[int, int] | None = None,
        tracer: ConversionTracer | None = None,
        animation_payload: dict[str, Any] | None = None,
    ) -> DrawingMLRenderResult:
        """Return slide XML and collected assets for the supplied scene graph."""

        prev_tracer = self._tracer
        self._tracer = tracer
        self._asset_registry = AssetRegistry()
        self._next_media_index = 1
        self._next_navigation_index = 1
        self._seen_filter_relationships.clear()
        self._emf_manager.reset()
        self._mask_pipeline.reset(assets=self._assets, tracer=self._tracer)
        self._animation_pipeline.reset(animation_payload, tracer=self._tracer)
        self._text_renderer = DrawingMLTextRenderer(
            text_template=self._text_template,
            wordart_template=self._wordart_template,
            policy_for=self._policy_for,
            register_run_navigation=self._register_run_navigation,
            trace_writer=self._trace_writer,
            assets=self._assets,
            logger=logger,
        )
        self._shape_renderer = DrawingMLShapeRenderer(
            rectangle_template=self._rectangle_template,
            preset_template=self._preset_template,
            path_template=self._path_template,
            line_template=self._line_template,
            picture_template=self._picture_template,
            path_generator=self._path_generator,
            policy_for=self._policy_for,
            register_media=self._register_media,
            trace_writer=self._trace_writer,
            animation_pipeline=self._animation_pipeline,
            rasterizer=self._rasterizer,
            logger=logger,
        )
        self._trace_writer("render_start", metadata={"slide_size": slide_size})
        try:
            fragments, next_shape_id = self._render_elements(scene, next_id=2)
            self._max_shape_id = next_shape_id - 1
            placeholder = "<!-- SHAPES WILL BE INSERTED HERE -->"
            slide_width, slide_height = slide_size or DEFAULT_SLIDE_SIZE

            slide_xml = self._slide_template.replace("{SLIDE_WIDTH}", str(slide_width))
            slide_xml = slide_xml.replace("{SLIDE_HEIGHT}", str(slide_height))
            shapes_xml = "\n            ".join(fragments)

            # 2. Inject shapes into template fragments
            slide_xml = slide_xml.replace(placeholder, shapes_xml)
            animation_xml = self._build_animation_xml()
            if animation_xml:
                slide_xml = slide_xml.replace("</p:sld>", f"{animation_xml}\n</p:sld>")
            result = DrawingMLRenderResult(
                slide_xml=slide_xml,
                slide_size=(slide_width, slide_height),
                assets=self._assets.snapshot(),
            )
            self._trace_writer(
                "render_complete",
                metadata={
                    "fragment_count": len(fragments),
                    "media_assets": len(result.assets.media),
                    "mask_assets": len(result.assets.masks),
                    "font_plans": len(result.assets.fonts),
                },
            )
            return result
        finally:
            self._asset_registry = None
            self._mask_pipeline.clear()
            self._text_renderer = None
            self._shape_renderer = None
            self._animation_pipeline.reset(None)
            self._tracer = prev_tracer

    def render_scene_from_ir(
        self,
        scene: IRScene,
        *,
        default_slide_size: tuple[int, int] = DEFAULT_SLIDE_SIZE,
        tracer: ConversionTracer | None = None,
        animation_payload: dict[str, Any] | None = None,
        animations: list | None = None, # Add animations parameter
    ) -> DrawingMLRenderResult:
        """Convenience wrapper that derives slide size from an IRScene."""

        width_px = scene.width_px or 0.0
        height_px = scene.height_px or 0.0
        if width_px <= 0 or height_px <= 0:
            slide_size = default_slide_size
        else:
            slide_size = (px_to_emu(width_px), px_to_emu(height_px))

        payload = animation_payload or {}
        if animations is not None:
            # If animations are explicitly passed, use them
            # but preserve policy from the original payload
            new_payload: dict[str, Any] = {"definitions": animations}
            if isinstance(animation_payload, dict) and "policy" in animation_payload:
                new_payload["policy"] = animation_payload["policy"]
            payload = new_payload
        elif scene.animations:
            # Use scene animations, but preserve policy from animation_payload
            new_payload = {"definitions": scene.animations}
            if isinstance(animation_payload, dict) and "policy" in animation_payload:
                new_payload["policy"] = animation_payload["policy"]
            payload = new_payload

        return self.render_scene(
            scene.elements,
            slide_size=slide_size,
            tracer=tracer,
            animation_payload=payload,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render_elements(self, elements: Iterable, next_id: int) -> tuple[list[str], int]:
        fragments: list[str] = []
        current_id = next_id
        for element in elements:
            rendered = self._render_element(element, current_id)
            if rendered is None:
                continue
            fragments.append(rendered[0])
            current_id = rendered[1]
        return fragments, current_id

    @staticmethod
    def _policy_for(metadata: dict[str, object] | None, target: str) -> dict[str, object]:
        if not metadata:
            return {}
        policy = metadata.get("policy")
        if not isinstance(policy, dict):
            return {}
        target_meta = policy.get(target)
        if isinstance(target_meta, dict):
            return target_meta
        return {}

    def _trace_writer(
        self,
        action: str,
        *,
        metadata: dict[str, object] | None = None,
        subject: str | None = None,
        stage: str = "writer",
    ) -> None:
        tracer = self._tracer
        if tracer is None:
            return
        tracer.record_stage_event(stage=stage, action=action, metadata=metadata, subject=subject)

    def _register_media(self, image: Image) -> str:
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
                self._assets.add_media(
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
            self._trace_writer(
                "media_registered",
                stage="media",
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

        r_id = f"rId{self._next_media_index}"
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
        self._assets.add_media(
            relationship_id=r_id,
            filename=filename,
            data=data_bytes,
            content_type=content_type,
            source="image",
        )
        metadata = image.metadata if isinstance(image.metadata, dict) else {}
        self._trace_writer(
            "media_registered",
            stage="media",
            metadata={
                "format": ext,
                "relationship_id": r_id,
                "width_px": getattr(image.size, "width", None),
                "height_px": getattr(image.size, "height", None),
                "image_source": metadata.get("image_source"),
                "data_bytes": len(data_bytes),
            },
        )
        return r_id

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
                if not isinstance(data_hex, str) or not data_hex:
                    continue

                asset_type = asset.get("type")
                if asset_type == "emf":
                    binary = bytes.fromhex(data_hex)
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
                    self._assets.add_media(
                        relationship_id=rel_id,
                        filename=entry.filename,
                        data=entry.data,
                        content_type="image/x-emf",
                        width_emu=entry.width_emu,
                        height_emu=entry.height_emu,
                        source="filter",
                    )
                    self._trace_writer(
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
                binary = bytes.fromhex(data_hex)
                rel_id = asset.get("relationship_id")
                if not isinstance(rel_id, str) or not rel_id:
                    rel_id = f"rId{self._next_media_index}"
                    asset["relationship_id"] = rel_id
                if rel_id in self._seen_filter_relationships:
                    continue
                filename = f"media_{self._next_media_index}.{ext}"
                self._next_media_index += 1
                self._assets.add_media(
                    relationship_id=rel_id,
                    filename=filename,
                    data=binary,
                    content_type=content_type,
                    source="filter",
                )
                self._trace_writer(
                    "filter_asset_registered",
                    stage="filter",
                    metadata={
                        "format": content_type,
                        "relationship_id": rel_id,
                    },
                )
                self._seen_filter_relationships.add(rel_id)

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

    def _render_element(self, element, shape_id: int) -> tuple[str, int] | None:
        metadata = getattr(element, "metadata", None)
        if isinstance(metadata, dict):
            self.register_filter_assets(metadata)
        else:
            metadata = {}
        self._animation_pipeline.register_mapping(metadata, shape_id)

        clip_xml, clip_diags = clip_xml_for(getattr(element, "clip", None))
        mask_xml, mask_diags = self._mask_pipeline.render(element)
        
        if mask_xml == "<!-- HIDDEN -->":
            mask_xml = ""
            if hasattr(element, "opacity"):
                try:
                    element = replace(element, opacity=0.0)
                except TypeError:
                    pass
            # For TextFrame, we rely on mask_xml propagation or handling downstream, 
            # but TextFrame doesn't support opacity override easily.
            # However, ShapeRenderer handles other types.
            # If element is Group, we might need to handle children?
            # Group has opacity.
            
        # Uniform opacity mask shortcut: multiply alpha into fill/stroke.
        mask_alpha = metadata.pop("_mask_alpha", None) if isinstance(metadata, dict) else None
        if mask_alpha is not None and 0.0 < mask_alpha < 1.0:
            element = _apply_mask_alpha(element, mask_alpha)
            self._trace_writer(
                "mask_alpha_shortcut",
                stage="mask",
                metadata={
                    "shape_id": shape_id,
                    "alpha": mask_alpha,
                    "element_type": type(element).__name__,
                },
            )

        if mask_xml:
            self._trace_writer(
                "mask_applied",
                stage="mask",
                metadata={
                    "shape_id": shape_id,
                    "length": len(mask_xml),
                    "element_type": type(element).__name__,
                },
            )
        for message in clip_diags:
            self._assets.add_diagnostic(message)
        for message in mask_diags:
            self._assets.add_diagnostic(message)
            logger.warning(message)
        hyperlink_xml = ""

        if isinstance(metadata, dict) and not isinstance(element, Group):
            hyperlink_xml = self._navigation_from_metadata(metadata, scope="shape") or ""

        if isinstance(element, TextFrame):
            if self._text_renderer is None:
                raise RuntimeError("Text renderer not initialised for current rendering run.")
            return self._text_renderer.render(
                element,
                shape_id,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_xml,
                mask_xml=mask_xml,
            )
        if isinstance(element, Group):
            if hyperlink_xml:
                if self._assets is not None:
                    self._assets.add_diagnostic("Group-level navigation is not yet supported; hyperlink ignored.")
                logger.warning("Navigation on group elements is not supported; skipping hyperlink metadata.")
            fragments, next_id = self._render_elements(element.children, shape_id)
            if not fragments:
                return None
            return "\n".join(fragments), next_id

        if self._shape_renderer is None:
            raise RuntimeError("Shape renderer not initialised for current rendering run.")
        rendered = self._shape_renderer.render(
            element,
            shape_id,
            metadata,
            hyperlink_xml=hyperlink_xml,
            clip_path_xml=clip_xml,
            mask_xml=mask_xml,
        )
        if rendered is not None:
            return rendered

        logger.debug("Skipping unsupported IR element type: %s", type(element).__name__)
        return None

    def _register_run_navigation(self, navigation, text_segment: str):
        return self._register_navigation_asset(navigation, scope="text_run", text=text_segment)

    def _navigation_from_metadata(self, metadata: dict[str, object], *, scope: str) -> str:
        nav_data = metadata.get("navigation")
        if nav_data is None:
            return ""
        entries = nav_data if isinstance(nav_data, list) else [nav_data]
        for entry in entries:
            elem = self._register_navigation_asset(entry, scope=scope)
            if elem is not None:
                from .xml_builder import to_string as _ts
                return _ts(elem)
        return ""

    def _register_navigation_asset(self, navigation, *, scope: str, text: str | None = None):
        if navigation is None or self._asset_registry is None:
            return None

        return register_navigation(
            navigation,
            scope=scope,
            text=text,
            allocate_rel_id=self._allocate_navigation_rid,
            add_asset=lambda asset: self._assets.add_navigation(
                relationship_id=asset.relationship_id,
                relationship_type=asset.relationship_type,
                target=asset.target,
                target_mode=asset.target_mode,
                action=asset.action,
                tooltip=asset.tooltip,
                history=asset.history,
                scope=asset.scope,
                text=asset.text,
            ),
        )

    def _build_animation_xml(self) -> str:
        return self._animation_pipeline.build(max_shape_id=getattr(self, '_max_shape_id', 0))

    def _allocate_navigation_rid(self) -> str:
        rid = f"rIdNav{self._next_navigation_index}"
        self._next_navigation_index += 1
        return rid


__all__ = ["DrawingMLWriter", "DrawingMLRenderResult", "DEFAULT_SLIDE_SIZE", "EMU_PER_PX"]
