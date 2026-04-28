"""SVG path parsing helpers for curve text positioning."""

from __future__ import annotations

import math
import re

from svg2ooxml.common.geometry.algorithms.curve_text_types import PathSegment
from svg2ooxml.ir.geometry import Point

_PATH_COMMAND_RE = r"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)"
_PATH_NUMBER_RE = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"


def parse_path_segments(path_data: str) -> list[PathSegment]:
    """Parse SVG path data into segments."""
    segments = []

    commands = parse_path_commands(path_data)
    if not commands:
        return []

    current_point = Point(0.0, 0.0)
    start_point = Point(0.0, 0.0)

    for cmd_tuple in commands:
        cmd = cmd_tuple[0]
        args = list(cmd_tuple[1:]) if len(cmd_tuple) > 1 else []

        if cmd.islower() and cmd.upper() != "Z":
            cmd = cmd.upper()
            for i in range(0, len(args), 2):
                if i + 1 < len(args):
                    args[i] += current_point.x
                    args[i + 1] += current_point.y

        if cmd == "M":
            if len(args) >= 2:
                current_point = Point(args[0], args[1])
                start_point = current_point

        elif cmd == "L":
            if len(args) >= 2:
                end_point = Point(args[0], args[1])
                segments.append(create_line_segment(current_point, end_point))
                current_point = end_point

        elif cmd == "C":
            if len(args) >= 6:
                cp1 = Point(args[0], args[1])
                cp2 = Point(args[2], args[3])
                end_point = Point(args[4], args[5])
                segments.append(create_cubic_segment(current_point, cp1, cp2, end_point))
                current_point = end_point

        elif cmd == "Q":
            if len(args) >= 4:
                cp = Point(args[0], args[1])
                end_point = Point(args[2], args[3])
                segments.append(create_quadratic_segment(current_point, cp, end_point))
                current_point = end_point

        elif cmd == "A":
            if len(args) >= 7:
                rx, ry = abs(args[0]), abs(args[1])
                large_arc = bool(args[3])
                sweep = bool(args[4])
                end_point = Point(args[5], args[6])

                if rx == 0 or ry == 0 or current_point == end_point:
                    segments.append(create_line_segment(current_point, end_point))
                else:
                    mid_x = (current_point.x + end_point.x) / 2.0
                    mid_y = (current_point.y + end_point.y) / 2.0
                    offset = min(rx, ry) * (0.5 if large_arc else 0.2)
                    if sweep:
                        mid_y += offset
                    else:
                        mid_y -= offset

                    midpoint = Point(mid_x, mid_y)
                    segments.append(create_line_segment(current_point, midpoint))
                    segments.append(create_line_segment(midpoint, end_point))

                current_point = end_point

        elif cmd == "Z":
            if current_point != start_point:
                segments.append(create_line_segment(current_point, start_point))
                current_point = start_point

    return segments


def parse_path_commands(path_data: str) -> list[tuple]:
    """Parse SVG path data into command tuples."""
    commands = []

    for match in re.finditer(_PATH_COMMAND_RE, path_data):
        cmd = match.group(1)
        params_str = match.group(2).strip()

        if params_str:
            params = [float(num) for num in re.findall(_PATH_NUMBER_RE, params_str)]
            if params:
                commands.append((cmd, *params))
            else:
                commands.append((cmd,))
        else:
            commands.append((cmd,))

    return commands


def create_line_segment(start: Point, end: Point) -> PathSegment:
    """Create line segment."""
    length = math.sqrt((end.x - start.x) ** 2 + (end.y - start.y) ** 2)
    return PathSegment(
        start_point=start,
        end_point=end,
        control_points=[],
        segment_type="line",
        length=length,
    )


def create_cubic_segment(start: Point, cp1: Point, cp2: Point, end: Point) -> PathSegment:
    """Create cubic Bezier segment."""
    length = (
        math.sqrt((cp1.x - start.x) ** 2 + (cp1.y - start.y) ** 2)
        + math.sqrt((cp2.x - cp1.x) ** 2 + (cp2.y - cp1.y) ** 2)
        + math.sqrt((end.x - cp2.x) ** 2 + (end.y - cp2.y) ** 2)
    )
    return PathSegment(
        start_point=start,
        end_point=end,
        control_points=[cp1, cp2],
        segment_type="cubic",
        length=length,
    )


def create_quadratic_segment(start: Point, cp: Point, end: Point) -> PathSegment:
    """Create quadratic Bezier segment."""
    length = math.sqrt((cp.x - start.x) ** 2 + (cp.y - start.y) ** 2) + math.sqrt(
        (end.x - cp.x) ** 2 + (end.y - cp.y) ** 2
    )
    return PathSegment(
        start_point=start,
        end_point=end,
        control_points=[cp],
        segment_type="quadratic",
        length=length,
    )


__all__ = [
    "create_cubic_segment",
    "create_line_segment",
    "create_quadratic_segment",
    "parse_path_commands",
    "parse_path_segments",
]
