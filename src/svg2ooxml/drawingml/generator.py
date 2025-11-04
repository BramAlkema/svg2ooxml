"""DrawingML geometry generation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple

from svg2ooxml.common.geometry.paths.drawingml import (
    PathCommand,
    build_path_commands,
    compute_path_bounds,
)
from svg2ooxml.ir.geometry import Point, Rect, SegmentType

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string

EMU_PER_PX = 9525


def px_to_emu(value: float | None) -> int:
    if value is None:
        return 0
    return max(0, int(round(value * EMU_PER_PX)))


@dataclass
class CustomGeometry:
    xml: str
    width_emu: int
    height_emu: int
    bounds: Rect


class DrawingMLPathGenerator:
    """Generate DrawingML path geometry from IR segments."""

    def generate_custom_geometry(
        self,
        segments: Iterable[SegmentType],
        *,
        fill_mode: str,
        stroke_mode: str,
        closed: bool,
    ) -> CustomGeometry:
        segment_list: list[SegmentType] = list(segments)
        if not segment_list:
            raise ValueError("DrawingMLPathGenerator requires at least one segment")

        bounds_px = compute_path_bounds(segment_list)
        width_emu = max(px_to_emu(bounds_px.width), 1)
        height_emu = max(px_to_emu(bounds_px.height), 1)

        commands = build_path_commands(segment_list, closed=closed)
        if not commands:
            raise ValueError("Path command list cannot be empty")

        # Build custom geometry using lxml
        custGeom = a_elem("custGeom")
        a_sub(custGeom, "avLst")
        a_sub(custGeom, "gdLst")
        a_sub(custGeom, "ahLst")
        a_sub(custGeom, "cxnLst")

        # Add path list with path
        pathLst = a_sub(custGeom, "pathLst")
        path = a_sub(pathLst, "path", w=width_emu, h=height_emu, fill=fill_mode, stroke=stroke_mode)

        # Add all path commands
        for cmd in commands:
            cmd_elem = self._command_to_xml(cmd, bounds_px)
            path.append(cmd_elem)

        geometry_xml = to_string(custGeom)

        return CustomGeometry(
            xml=geometry_xml,
            width_emu=width_emu,
            height_emu=height_emu,
            bounds=bounds_px,
        )

    def _command_to_xml(self, command: PathCommand, bounds: Rect):
        """Convert path command to lxml element."""
        if command.name == "moveTo":
            point = command.points[0]
            x, y = self._point_to_emu(point, bounds)
            moveTo = a_elem("moveTo")
            a_sub(moveTo, "pt", x=x, y=y)
            return moveTo
        if command.name == "lnTo":
            point = command.points[0]
            x, y = self._point_to_emu(point, bounds)
            lnTo = a_elem("lnTo")
            a_sub(lnTo, "pt", x=x, y=y)
            return lnTo
        if command.name == "cubicBezTo":
            c1x, c1y = self._point_to_emu(command.points[0], bounds)
            c2x, c2y = self._point_to_emu(command.points[1], bounds)
            ex, ey = self._point_to_emu(command.points[2], bounds)
            cubicBezTo = a_elem("cubicBezTo")
            a_sub(cubicBezTo, "pt", x=c1x, y=c1y)
            a_sub(cubicBezTo, "pt", x=c2x, y=c2y)
            a_sub(cubicBezTo, "pt", x=ex, y=ey)
            return cubicBezTo
        if command.name == "close":
            return a_elem("close")
        raise ValueError(f"Unsupported path command: {command.name}")

    def _point_to_emu(self, point: Point, bounds: Rect) -> Tuple[int, int]:
        return px_to_emu(point.x - bounds.x), px_to_emu(point.y - bounds.y)

__all__ = ["DrawingMLPathGenerator", "CustomGeometry", "EMU_PER_PX", "px_to_emu"]
