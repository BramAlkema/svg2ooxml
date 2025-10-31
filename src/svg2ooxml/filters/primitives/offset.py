"""feOffset filter primitive."""

from __future__ import annotations

from dataclasses import dataclass
import math

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import parse_number
from svg2ooxml.units.conversion import px_to_emu


@dataclass
class OffsetParams:
    dx: float
    dy: float


class OffsetFilter(Filter):
    primitive_tags = ("feOffset",)
    filter_type = "offset"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = self._parse_params(primitive)
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

    def _parse_params(self, primitive: etree._Element) -> OffsetParams:
        dx = parse_number(primitive.get("dx"))
        dy = parse_number(primitive.get("dy"))
        return OffsetParams(dx=dx, dy=dy)

    def _build_drawingml(self, dx_emu: int, dy_emu: int) -> str:
        distance = int(math.hypot(dx_emu, dy_emu))
        if distance == 0:
            return "<a:effectLst/>"

        # PowerPoint angle (0 = right, counter-clockwise positive, units 60000 per degree)
        angle_rad = math.atan2(dy_emu, dx_emu)
        ppt_angle = int((math.degrees(angle_rad) * 60000) % 21600000)
        distance = min(distance, 914400)

        return (
            "<a:effectLst>"
            f"<a:outerShdw blurRad=\"0\" dist=\"{distance}\" dir=\"{ppt_angle}\" algn=\"ctr\">"
            "<a:srgbClr val=\"000000\"><a:alpha val=\"0\"/></a:srgbClr>"
            "</a:outerShdw>"
            "</a:effectLst>"
        )


__all__ = ["OffsetFilter"]
