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

        commands_xml = "\n        ".join(self._command_to_xml(cmd, bounds_px) for cmd in commands)
        geometry_xml = (
            "<a:custGeom>\n"
            "      <a:avLst/>\n"
            "      <a:gdLst/>\n"
            "      <a:ahLst/>\n"
            "      <a:cxnLst/>\n"
            "      <a:pathLst>\n"
            f'        <a:path w="{width_emu}" h="{height_emu}" fill="{fill_mode}" stroke="{stroke_mode}">\n'
            f"        {commands_xml}\n"
            "        </a:path>\n"
            "      </a:pathLst>\n"
            "    </a:custGeom>"
        )
        return CustomGeometry(
            xml=geometry_xml,
            width_emu=width_emu,
            height_emu=height_emu,
            bounds=bounds_px,
        )

    def _command_to_xml(self, command: PathCommand, bounds: Rect) -> str:
        if command.name == "moveTo":
            point = command.points[0]
            x, y = self._point_to_emu(point, bounds)
            return f'<a:moveTo><a:pt x="{x}" y="{y}"/></a:moveTo>'
        if command.name == "lnTo":
            point = command.points[0]
            x, y = self._point_to_emu(point, bounds)
            return f'<a:lnTo><a:pt x="{x}" y="{y}"/></a:lnTo>'
        if command.name == "cubicBezTo":
            c1x, c1y = self._point_to_emu(command.points[0], bounds)
            c2x, c2y = self._point_to_emu(command.points[1], bounds)
            ex, ey = self._point_to_emu(command.points[2], bounds)
            return (
                "<a:cubicBezTo>"
                f'<a:pt x="{c1x}" y="{c1y}"/>'
                f'<a:pt x="{c2x}" y="{c2y}"/>'
                f'<a:pt x="{ex}" y="{ey}"/>'
                "</a:cubicBezTo>"
            )
        if command.name == "close":
            return "<a:close/>"
        raise ValueError(f"Unsupported path command: {command.name}")

    def _point_to_emu(self, point: Point, bounds: Rect) -> Tuple[int, int]:
        return px_to_emu(point.x - bounds.x), px_to_emu(point.y - bounds.y)

__all__ = ["DrawingMLPathGenerator", "CustomGeometry", "EMU_PER_PX", "px_to_emu"]
