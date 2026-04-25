"""feFlood filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.color.utils import color_to_hex
from svg2ooxml.common.conversions.opacity import opacity_to_ppt, parse_opacity

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
from svg2ooxml.filters.base import Filter, FilterContext, FilterResult


def _normalise_color(value: str | None) -> str:
    return color_to_hex(value, default="000000")


@dataclass
class FloodParams:
    color: str
    opacity: float


class FloodFilter(Filter):
    primitive_tags = ("feFlood",)
    filter_type = "flood"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = self._parse_params(primitive)
        metadata = {
            "filter_type": self.filter_type,
            "color": params.color,
            "opacity": params.opacity,
            "flood_color": params.color,
            "flood_opacity": params.opacity,
        }
        alpha = opacity_to_ppt(params.opacity)

        # Build effectLst with solidFill
        effectLst = a_elem("effectLst")
        solidFill = a_sub(effectLst, "solidFill")
        srgbClr = a_sub(solidFill, "srgbClr", val=params.color)
        a_sub(srgbClr, "alpha", val=alpha)

        drawingml = to_string(effectLst)
        return FilterResult(success=True, drawingml=drawingml, metadata=metadata)

    def _parse_params(self, primitive: etree._Element) -> FloodParams:
        style_map = self._parse_style(primitive.get("style"))
        color = _normalise_color(primitive.get("flood-color") or style_map.get("flood-color"))
        opacity = parse_opacity(
            primitive.get("flood-opacity") or style_map.get("flood-opacity"),
            default=1.0,
        )
        return FloodParams(color=color, opacity=opacity)

    @staticmethod
    def _parse_style(value: str | None) -> dict[str, str]:
        if not value:
            return {}
        properties: dict[str, str] = {}
        for part in value.split(";"):
            if ":" not in part:
                continue
            key, raw = part.split(":", 1)
            properties[key.strip()] = raw.strip()
        return properties


__all__ = ["FloodFilter"]
