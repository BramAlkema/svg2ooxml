"""feImage filter primitive."""

from __future__ import annotations

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
        fallback = "bitmap" if not params.href else None
        warnings = []
        if params.href is None:
            warnings.append("feImage without href")
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


__all__ = ["ImageFilter"]
