"""Command handlers for SVG path parsing."""

from __future__ import annotations

from svg2ooxml.common.geometry.paths.parser_arcs import _parse_arc
from svg2ooxml.common.geometry.paths.parser_geometry import (
    _resolve_relative_point,
)
from svg2ooxml.common.geometry.paths.parser_tokens import _take_numbers
from svg2ooxml.common.geometry.paths.parser_types import PathParseError, Token
from svg2ooxml.common.geometry.paths.quadratic import quadratic_to_cubic
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType


def _parse_moveto(
    tokens: list[Token],
    index: int,
    command: str,
    cursor: Point,
    segments: list[SegmentType],
) -> tuple[Point, Point, int]:
    is_relative = command == "m"
    numbers, index = _take_numbers(tokens, index, 2, allow_multiple=True)
    if len(numbers) < 2:
        raise PathParseError("moveto requires coordinate pair")

    start_point: Point | None = None
    current = cursor
    first = True
    for i in range(0, len(numbers), 2):
        x, y = numbers[i], numbers[i + 1]
        target = Point(current.x + x, current.y + y) if is_relative else Point(x, y)
        if first:
            current = target
            start_point = target
            first = False
        else:
            segments.append(LineSegment(current, target))
            current = target
    return current, (start_point or current), index


def _parse_lineto(
    tokens: list[Token],
    index: int,
    command: str,
    cursor: Point,
    segments: list[SegmentType],
) -> tuple[Point, int]:
    is_relative = command == "l"
    numbers, index = _take_numbers(tokens, index, 2, allow_multiple=True)
    if len(numbers) % 2 != 0:
        raise PathParseError("lineto requires coordinate pairs")

    for i in range(0, len(numbers), 2):
        x, y = numbers[i], numbers[i + 1]
        target = Point(cursor.x + x, cursor.y + y) if is_relative else Point(x, y)
        segments.append(LineSegment(cursor, target))
        cursor = target
    return cursor, index


def _parse_horizontal(
    tokens: list[Token],
    index: int,
    command: str,
    cursor: Point,
    segments: list[SegmentType],
) -> tuple[Point, int]:
    is_relative = command == "h"
    numbers, index = _take_numbers(tokens, index, 1, allow_multiple=True)

    for value in numbers:
        target_x = cursor.x + value if is_relative else value
        target = Point(target_x, cursor.y)
        segments.append(LineSegment(cursor, target))
        cursor = target
    return cursor, index


def _parse_vertical(
    tokens: list[Token],
    index: int,
    command: str,
    cursor: Point,
    segments: list[SegmentType],
) -> tuple[Point, int]:
    is_relative = command == "v"
    numbers, index = _take_numbers(tokens, index, 1, allow_multiple=True)

    for value in numbers:
        target_y = cursor.y + value if is_relative else value
        target = Point(cursor.x, target_y)
        segments.append(LineSegment(cursor, target))
        cursor = target
    return cursor, index


def _parse_cubic(
    tokens: list[Token],
    index: int,
    command: str,
    cursor: Point,
    segments: list[SegmentType],
) -> tuple[Point, Point | None, int]:
    is_relative = command == "c"
    numbers, index = _take_numbers(tokens, index, 6, allow_multiple=True)
    if len(numbers) % 6 != 0:
        raise PathParseError("cubic curve requires sets of six numbers")

    last_control: Point | None = None
    for i in range(0, len(numbers), 6):
        x1, y1, x2, y2, x, y = numbers[i : i + 6]
        control1 = _resolve_relative_point(cursor, x1, y1, is_relative)
        control2 = _resolve_relative_point(cursor, x2, y2, is_relative)
        target = _resolve_relative_point(cursor, x, y, is_relative)
        segments.append(BezierSegment(cursor, control1, control2, target))
        cursor = target
        last_control = control2
    return cursor, last_control, index


def _parse_smooth_cubic(
    tokens: list[Token],
    index: int,
    command: str,
    cursor: Point,
    segments: list[SegmentType],
    last_cubic_control: Point | None,
) -> tuple[Point, Point | None, int]:
    is_relative = command == "s"
    numbers, index = _take_numbers(tokens, index, 4, allow_multiple=True)
    if len(numbers) % 4 != 0:
        raise PathParseError("smooth cubic curve requires sets of four numbers")

    for i in range(0, len(numbers), 4):
        x1, y1, x, y = numbers[i : i + 4]
        control1 = (
            Point(2 * cursor.x - last_cubic_control.x, 2 * cursor.y - last_cubic_control.y)
            if last_cubic_control is not None
            else cursor
        )
        control2 = _resolve_relative_point(cursor, x1, y1, is_relative)
        target = _resolve_relative_point(cursor, x, y, is_relative)
        segments.append(BezierSegment(cursor, control1, control2, target))
        cursor = target
        last_cubic_control = control2
    return cursor, last_cubic_control, index


def _parse_quadratic(
    tokens: list[Token],
    index: int,
    command: str,
    cursor: Point,
    segments: list[SegmentType],
) -> tuple[Point, Point | None, int]:
    is_relative = command == "q"
    numbers, index = _take_numbers(tokens, index, 4, allow_multiple=True)
    if len(numbers) % 4 != 0:
        raise PathParseError("quadratic curve requires sets of four numbers")

    last_control: Point | None = None
    for i in range(0, len(numbers), 4):
        x1, y1, x, y = numbers[i : i + 4]
        control = _resolve_relative_point(cursor, x1, y1, is_relative)
        target = _resolve_relative_point(cursor, x, y, is_relative)
        segments.append(quadratic_to_cubic(cursor, control, target))
        cursor = target
        last_control = control
    return cursor, last_control, index


def _parse_smooth_quadratic(
    tokens: list[Token],
    index: int,
    command: str,
    cursor: Point,
    segments: list[SegmentType],
    last_quadratic_control: Point | None,
) -> tuple[Point, Point | None, int]:
    is_relative = command == "t"
    numbers, index = _take_numbers(tokens, index, 2, allow_multiple=True)
    if len(numbers) % 2 != 0:
        raise PathParseError("smooth quadratic curve requires coordinate pairs")

    for i in range(0, len(numbers), 2):
        x, y = numbers[i : i + 2]
        control = (
            Point(2 * cursor.x - last_quadratic_control.x, 2 * cursor.y - last_quadratic_control.y)
            if last_quadratic_control is not None
            else cursor
        )
        target = _resolve_relative_point(cursor, x, y, is_relative)
        segments.append(quadratic_to_cubic(cursor, control, target))
        cursor = target
        last_quadratic_control = control
    return cursor, last_quadratic_control, index


__all__ = [
    "_parse_arc",
    "_parse_cubic",
    "_parse_horizontal",
    "_parse_lineto",
    "_parse_moveto",
    "_parse_quadratic",
    "_parse_smooth_cubic",
    "_parse_smooth_quadratic",
    "_parse_vertical",
]
