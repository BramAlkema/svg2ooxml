"""Drop shadow and glow filter primitives."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import parse_number
from svg2ooxml.units.conversion import px_to_emu

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string


@dataclass
class DropShadowParams:
    dx: float
    dy: float
    std_dev: float
    flood_color: str
    flood_opacity: float


class DropShadowFilter(Filter):
    primitive_tags = ("feDropShadow",)
    filter_type = "drop_shadow"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = self._parse_params(primitive)
        shadow_xml = self._to_drawingml(params)
        metadata = {
            "filter_type": self.filter_type,
            "dx": params.dx,
            "dy": params.dy,
            "std_dev": params.std_dev,
            "color": params.flood_color,
            "opacity": params.flood_opacity,
        }
        return FilterResult(success=True, drawingml=shadow_xml, metadata=metadata)

    def _parse_params(self, primitive: etree._Element) -> DropShadowParams:
        dx = parse_number(primitive.get("dx"))
        dy = parse_number(primitive.get("dy"))
        std_dev = parse_number(primitive.get("stdDeviation"))
        flood_color = primitive.get("flood-color", "000000").lstrip("#").upper()
        if len(flood_color) == 3:
            flood_color = "".join(ch * 2 for ch in flood_color)
        try:
            flood_opacity = float(primitive.get("flood-opacity", "1"))
        except ValueError:
            flood_opacity = 1.0
        flood_opacity = max(0.0, min(flood_opacity, 1.0))
        return DropShadowParams(dx=dx, dy=dy, std_dev=std_dev, flood_color=flood_color, flood_opacity=flood_opacity)

    def _to_drawingml(self, params: DropShadowParams) -> str:
        blur_radius = int(px_to_emu(max(0.0, params.std_dev * 2.0)))
        offset_x = int(px_to_emu(params.dx))
        offset_y = int(px_to_emu(params.dy))
        alpha = int(params.flood_opacity * 100000)
        dist = int((offset_x ** 2 + offset_y ** 2) ** 0.5)
        direction = self._compute_direction(params.dx, params.dy)

        effectLst = a_elem("effectLst")
        outerShdw = a_sub(effectLst, "outerShdw", blurRad=blur_radius, dist=dist, dir=direction, algn="ctr", rotWithShape="0")
        srgbClr = a_sub(outerShdw, "srgbClr", val=params.flood_color)
        a_sub(srgbClr, "alpha", val=alpha)

        return to_string(effectLst)

    def _compute_direction(self, dx: float, dy: float) -> int:
        import math

        if dx == 0 and dy == 0:
            return 0
        angle = math.degrees(math.atan2(-dy, dx))  # SVG y-positive downward, PPT angle measured counter-clockwise from +x
        return int((angle % 360) * 60000)


class GlowFilter(Filter):
    primitive_tags = ("feGlow",)
    filter_type = "glow"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        radius = parse_number(primitive.get("stdDeviation")) * 2.0
        color = (primitive.get("flood-color") or "FFFFFF").lstrip("#").upper()
        if len(color) == 3:
            color = "".join(ch * 2 for ch in color)
        opacity = parse_number(primitive.get("flood-opacity"), default=1.0)
        blur_radius = int(px_to_emu(max(0.0, radius)))
        alpha = int(max(0.0, min(opacity, 1.0)) * 100000)

        effectLst = a_elem("effectLst")
        glow_elem = a_sub(effectLst, "glow", rad=blur_radius)
        srgbClr = a_sub(glow_elem, "srgbClr", val=color)
        a_sub(srgbClr, "alpha", val=alpha)

        drawingml = to_string(effectLst)
        metadata = {
            "filter_type": self.filter_type,
            "radius": radius,
            "color": color,
            "opacity": opacity,
        }
        return FilterResult(success=True, drawingml=drawingml, metadata=metadata)


__all__ = ["DropShadowFilter", "GlowFilter"]
