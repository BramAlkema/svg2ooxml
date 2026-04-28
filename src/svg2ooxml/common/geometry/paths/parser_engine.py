"""State machine for SVG path data parsing."""

from __future__ import annotations

from svg2ooxml.common.geometry.paths.parser_commands import (
    _parse_arc,
    _parse_cubic,
    _parse_horizontal,
    _parse_lineto,
    _parse_moveto,
    _parse_quadratic,
    _parse_smooth_cubic,
    _parse_smooth_quadratic,
    _parse_vertical,
)
from svg2ooxml.common.geometry.paths.parser_tokens import _tokenize
from svg2ooxml.common.geometry.paths.parser_types import PathParseError
from svg2ooxml.ir.geometry import LineSegment, Point, SegmentType


def _parse_path_data(data: str) -> tuple[SegmentType, ...]:
    tokens = _tokenize(data)
    segments: list[SegmentType] = []

    cursor = Point(0.0, 0.0)
    start_point: Point | None = None
    last_cubic_control: Point | None = None
    last_quadratic_control: Point | None = None
    command: str | None = None
    index = 0

    while index < len(tokens):
        token = tokens[index]
        if isinstance(token, str):
            command = token
            index += 1
        elif command is None:
            raise PathParseError("Path data missing initial command")

        if command in {"M", "m"}:
            cursor, start_point, index = _parse_moveto(tokens, index, command, cursor, segments)
            command = "L" if command == "M" else "l"
            last_cubic_control = None
            last_quadratic_control = None
        elif command in {"L", "l"}:
            cursor, index = _parse_lineto(tokens, index, command, cursor, segments)
            last_cubic_control = None
            last_quadratic_control = None
        elif command in {"H", "h"}:
            cursor, index = _parse_horizontal(tokens, index, command, cursor, segments)
            last_cubic_control = None
            last_quadratic_control = None
        elif command in {"V", "v"}:
            cursor, index = _parse_vertical(tokens, index, command, cursor, segments)
            last_cubic_control = None
            last_quadratic_control = None
        elif command in {"C", "c"}:
            cursor, last_cubic_control, index = _parse_cubic(tokens, index, command, cursor, segments)
            last_quadratic_control = None
        elif command in {"S", "s"}:
            cursor, last_cubic_control, index = _parse_smooth_cubic(
                tokens,
                index,
                command,
                cursor,
                segments,
                last_cubic_control,
            )
            last_quadratic_control = None
        elif command in {"Q", "q"}:
            cursor, last_quadratic_control, index = _parse_quadratic(tokens, index, command, cursor, segments)
            last_cubic_control = None
        elif command in {"T", "t"}:
            cursor, last_quadratic_control, index = _parse_smooth_quadratic(
                tokens,
                index,
                command,
                cursor,
                segments,
                last_quadratic_control,
            )
            last_cubic_control = None
        elif command in {"A", "a"}:
            cursor, index = _parse_arc(tokens, index, command, cursor, segments)
            last_cubic_control = None
            last_quadratic_control = None
        elif command in {"Z", "z"}:
            if start_point is not None and (cursor.x != start_point.x or cursor.y != start_point.y):
                segments.append(LineSegment(cursor, start_point))
            cursor = start_point or cursor
            last_cubic_control = None
            last_quadratic_control = None
        else:
            raise PathParseError(f"Unsupported path command: {command}")

        if command in {"Z", "z"}:
            start_point = cursor

    return tuple(segments)


__all__ = ["_parse_path_data"]
