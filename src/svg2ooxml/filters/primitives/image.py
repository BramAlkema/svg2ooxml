"""feImage filter primitive."""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import build_exporter_hook

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
        href = primitive.get(XLINK_HREF) or primitive.get("href")
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
        services = getattr(context, "services", None)
        image_service = getattr(services, "image_service", None) if services is not None else None
        if image_service is None:
            return None
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
