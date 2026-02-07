"""feFlood filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.common.conversions.opacity import opacity_to_ppt

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import parse_number


def _normalise_color(value: str | None) -> str:
    token = (value or "#000000").strip()
    if token.startswith("#"):
        token = token[1:]
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    return token.upper()


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
        color = _normalise_color(primitive.get("flood-color"))
        opacity = max(0.0, min(parse_number(primitive.get("flood-opacity"), default=1.0), 1.0))
        return FloodParams(color=color, opacity=opacity)


__all__ = ["FloodFilter"]
