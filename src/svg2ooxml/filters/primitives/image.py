"""feImage filter primitive."""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from svg2ooxml.common.boundaries import classify_resource_href
from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import build_exporter_hook
from svg2ooxml.services.image_service import (
    ImageResource,
    ImageService,
    normalize_image_href,
    resolve_local_image_path,
)

XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


@dataclass
class ImageParams:
    href: str | None
    preserve_aspect_ratio: str | None
    cross_origin: str | None


class ImageFilter(Filter):
    primitive_tags = ("feImage",)
    filter_type = "image"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = self._parse_params(primitive)
        warnings: list[str] = []
        metadata = {
            "filter_type": self.filter_type,
            "href": params.href,
            "preserve_aspect_ratio": params.preserve_aspect_ratio,
            "cross_origin": params.cross_origin,
        }
        drawingml = build_exporter_hook(
            "image",
            {
                "href": params.href or "",
                "preserve_aspect_ratio": params.preserve_aspect_ratio or "",
                "cross_origin": params.cross_origin or "",
            },
        )
        asset = self._resolve_raster_asset(params.href, context, warnings=warnings)
        if asset:
            metadata["fallback_assets"] = [asset]
            metadata["image_resolved"] = True
            metadata["image_source"] = asset.get("source")
            metadata["native_support"] = False
        else:
            metadata["image_resolved"] = False

        fallback = "bitmap"
        if params.href is None:
            warnings.append("feImage without href")
        elif asset is None:
            warnings.append("feImage href could not be resolved")
        return FilterResult(
            success=True,
            drawingml=drawingml,
            fallback=fallback,
            metadata=metadata,
            warnings=warnings,
        )

    def _parse_params(self, primitive: etree._Element) -> ImageParams:
        raw_href = primitive.get(XLINK_HREF) or primitive.get("href")
        href = self._normalize_href(raw_href)
        preserve = primitive.get("preserveAspectRatio")
        cross_origin = primitive.get("crossorigin")
        return ImageParams(href=href, preserve_aspect_ratio=preserve, cross_origin=cross_origin)

    def _resolve_raster_asset(
        self,
        href: str | None,
        context: FilterContext,
        *,
        warnings: list[str],
    ) -> dict[str, object] | None:
        if not href:
            return None
        href = self._normalize_href(href)
        if not href:
            return None
        services = getattr(context, "services", None)
        image_service = getattr(services, "image_service", None) if services is not None else None
        resource = self._resolve_from_context(href, context)
        if (
            resource is None
            and image_service is not None
            and not self._context_should_bound_local_href(href, context)
        ):
            resource = image_service.resolve(href)
        if resource is None:
            return None

        png_bytes, width_px, height_px = self._resource_to_png(resource.data, warnings=warnings)
        if png_bytes is None:
            return None

        asset: dict[str, object] = {
            "type": "raster",
            "format": "png",
            "data": png_bytes,
        }
        if width_px is not None:
            asset["width_px"] = width_px
        if height_px is not None:
            asset["height_px"] = height_px
        if resource.source:
            asset["source"] = resource.source
        return asset

    def _context_should_bound_local_href(self, href: str, context: FilterContext) -> bool:
        reference = classify_resource_href(href)
        if reference is None or not reference.is_local_path:
            return False
        return self._resolve_base_dir(context) is not None

    def _resolve_from_context(self, href: str, context: FilterContext) -> ImageResource | None:
        href = self._normalize_href(href)
        if not href:
            return None
        reference = classify_resource_href(href)
        if reference is None:
            return None
        if reference.kind == "data":
            return ImageService._data_uri_resolver(reference.normalized)
        if not reference.is_local_path:
            return None

        base_dir = self._resolve_base_dir(context)
        if base_dir is None:
            return None

        try:
            allowed_root = self._resolve_asset_root(context, base_dir)
            target = resolve_local_image_path(
                reference.path or reference.normalized,
                base_dir,
                asset_root=allowed_root,
            )
            if target is None:
                return None
            return ImageResource(data=target.read_bytes(), source="file")
        except OSError:
            return None

    @staticmethod
    def _resolve_base_dir(context: FilterContext) -> Path | None:
        options = context.options if isinstance(context.options, dict) else {}
        for key in ("base_dir", "source_path", "svg_path", "svg_file"):
            value = options.get(key)
            if isinstance(value, str) and value:
                path = Path(value).expanduser().resolve()
                return path.parent if path.is_file() else path

        services = getattr(context, "services", None)
        if services is not None and hasattr(services, "resolve"):
            for key in ("base_dir", "source_path"):
                value = services.resolve(key)
                if isinstance(value, str) and value:
                    path = Path(value).expanduser().resolve()
                    return path.parent if path.is_file() else path
        return None

    @staticmethod
    def _normalize_href(href: str | None) -> str | None:
        return normalize_image_href(href)

    @staticmethod
    def _resolve_asset_root(context: FilterContext, base_dir: Path) -> Path | None:
        options = context.options if isinstance(context.options, dict) else {}
        for key in ("asset_root", "root_dir", "source_root"):
            value = options.get(key)
            if isinstance(value, str) and value:
                try:
                    return Path(value).expanduser().resolve()
                except Exception:
                    continue
        return base_dir

    def _resource_to_png(
        self,
        payload: bytes,
        *,
        warnings: list[str],
    ) -> tuple[bytes | None, int | None, int | None]:
        if self._is_png(payload):
            width_px, height_px = self._parse_png_size(payload)
            return payload, width_px, height_px

        try:
            from PIL import Image
        except Exception:
            warnings.append("feImage raster conversion skipped: Pillow not available")
            return None, None, None

        try:
            with Image.open(io.BytesIO(payload)) as image:
                image.load()
                width_px, height_px = image.size
                working = image
                if working.mode not in {"RGB", "RGBA"}:
                    working = working.convert("RGBA")
                buffer = io.BytesIO()
                working.save(buffer, format="PNG")
                return buffer.getvalue(), width_px, height_px
        except Exception as exc:
            warnings.append(f"feImage raster conversion failed: {exc}")
            return None, None, None

    @staticmethod
    def _is_png(payload: bytes) -> bool:
        return payload.startswith(b"\x89PNG\r\n\x1a\n")

    @staticmethod
    def _parse_png_size(payload: bytes) -> tuple[int | None, int | None]:
        if len(payload) < 24:
            return None, None
        try:
            width, height = struct.unpack(">II", payload[16:24])
            return int(width), int(height)
        except Exception:
            return None, None


__all__ = ["ImageFilter"]
