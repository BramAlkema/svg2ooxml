"""feOffset filter primitive."""

from __future__ import annotations

import math
from dataclasses import dataclass

from lxml import etree

from svg2ooxml.common.conversions.angles import radians_to_ppt
from svg2ooxml.common.units import px_to_emu
from svg2ooxml.common.units.scalars import EMU_PER_INCH

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils.parsing import parse_length


@dataclass
class OffsetParams:
    dx: float
    dy: float


class OffsetFilter(Filter):
    primitive_tags = ("feOffset",)
    filter_type = "offset"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = self._parse_params(primitive, context)
        metadata = {
            "filter_type": self.filter_type,
            "dx": params.dx,
            "dy": params.dy,
        }
        dx_emu = int(px_to_emu(params.dx))
        dy_emu = int(px_to_emu(params.dy))
        metadata["dx_emu"] = dx_emu
        metadata["dy_emu"] = dy_emu
        drawingml = self._build_drawingml(dx_emu, dy_emu)
        return FilterResult(success=True, drawingml=drawingml, metadata=metadata)

    def _parse_params(self, primitive: etree._Element, context: FilterContext) -> OffsetParams:
        dx = parse_length(primitive.get("dx"), context=context, axis="x")
        dy = parse_length(primitive.get("dy"), context=context, axis="y")
        return OffsetParams(dx=dx, dy=dy)

    def _build_drawingml(self, dx_emu: int, dy_emu: int) -> str:
        distance = int(math.hypot(dx_emu, dy_emu))

        effectLst = a_elem("effectLst")

        if distance == 0:
            return to_string(effectLst)

        # PowerPoint angle (0 = right, counter-clockwise positive, units 60000 per degree)
        angle_rad = math.atan2(dy_emu, dx_emu)
        ppt_angle = radians_to_ppt(angle_rad % (2 * math.pi))
        distance = min(distance, EMU_PER_INCH)

        # Create outer shadow with zero blur to simulate offset
        outerShdw = a_sub(effectLst, "outerShdw", blurRad="0", dist=distance, dir=ppt_angle, algn="ctr")
        srgbClr = a_sub(outerShdw, "srgbClr", val="000000")
        a_sub(srgbClr, "alpha", val="0")

        return to_string(effectLst)


__all__ = ["OffsetFilter"]
