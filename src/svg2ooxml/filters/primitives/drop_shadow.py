"""Drop shadow and glow filter primitives."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.color.utils import color_to_hex
from svg2ooxml.common.conversions.angles import degrees_to_ppt
from svg2ooxml.common.conversions.opacity import opacity_to_ppt, parse_opacity
from svg2ooxml.common.units import px_to_emu

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils.parsing import parse_length


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
        params = self._parse_params(primitive, context)
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

    def _parse_params(self, primitive: etree._Element, context: FilterContext) -> DropShadowParams:
        dx = parse_length(primitive.get("dx"), context=context, axis="x")
        dy = parse_length(primitive.get("dy"), context=context, axis="y")
        std_dev = parse_length(primitive.get("stdDeviation"), context=context, axis="x")
        flood_color = color_to_hex(primitive.get("flood-color"), default="000000")
        flood_opacity = parse_opacity(primitive.get("flood-opacity"), default=1.0)
        return DropShadowParams(dx=dx, dy=dy, std_dev=std_dev, flood_color=flood_color, flood_opacity=flood_opacity)

    def _to_drawingml(self, params: DropShadowParams) -> str:
        blur_radius = int(px_to_emu(max(0.0, params.std_dev * 2.0)))
        offset_x = int(px_to_emu(params.dx))
        offset_y = int(px_to_emu(params.dy))
        alpha = opacity_to_ppt(params.flood_opacity)
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
        return degrees_to_ppt(angle % 360)


class GlowFilter(Filter):
    primitive_tags = ("feGlow",)
    filter_type = "glow"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        radius = parse_length(primitive.get("stdDeviation"), context=context, axis="x") * 2.0
        color = color_to_hex(primitive.get("flood-color"), default="FFFFFF")
        opacity = parse_opacity(primitive.get("flood-opacity"), default=1.0)
        blur_radius = int(px_to_emu(max(0.0, radius)))
        alpha = opacity_to_ppt(opacity)

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
