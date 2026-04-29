"""Normalize SVG path data into absolute commands and flattened primitives."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from svg2ooxml.common.geometry.paths.flatten import (
    flatten_cubic_points,
    flatten_quadratic_points,
)
from svg2ooxml.common.geometry.paths.parser_arcs import approximate_arc
from svg2ooxml.common.geometry.paths.parser_tokens import _tokenize
from svg2ooxml.common.geometry.paths.parser_types import PathParseError, Token
from svg2ooxml.ir.geometry import BezierSegment, LineSegment
from svg2ooxml.ir.geometry import Point as IRPoint

from .matrix import Matrix
from .matrix_bridge import apply_matrix_to_xy
from .path_commands import (
    ARC_TO,
    CLOSE,
    CUBIC_TO,
    H_LINE_TO,
    LINE_TO,
    MOVE_TO,
    QUAD_TO,
    SMOOTH_CUBIC_TO,
    SMOOTH_QUAD_TO,
    V_LINE_TO,
)
from .primitives import ClosePath, LineTo, MoveTo

Number = float
Point = tuple[float, float]


@dataclass(frozen=True)
class PathCommand:
    command: str
    points: tuple[float, ...]


@dataclass(frozen=True)
class NormalizedPath:
    commands: tuple[PathCommand, ...]
    transform: Matrix
    stroke_width: float | None

    def as_fill_only(self) -> NormalizedPath:
        raise NotImplementedError("Stroke to fill conversion not yet implemented.")

    def to_primitives(self, tolerance: float = 0.25) -> tuple[object, ...]:
        primitives: list[object] = []
        current = (0.0, 0.0)
        start = (0.0, 0.0)
        prev_cubic_ctrl: Point | None = None
        prev_quad_ctrl: Point | None = None

        for cmd in self.commands:
            op = cmd.command
            pts = cmd.points

            if op == MOVE_TO:
                current = (pts[0], pts[1])
                start = current
                prev_cubic_ctrl = None
                prev_quad_ctrl = None
                primitives.append(_transform_primitive(MoveTo(*current), self.transform))
            elif op == LINE_TO:
                current = (pts[0], pts[1])
                prev_cubic_ctrl = None
                prev_quad_ctrl = None
                primitives.append(_transform_primitive(LineTo(*current), self.transform))
            elif op == CUBIC_TO:
                p0 = current
                p1 = (pts[0], pts[1])
                p2 = (pts[2], pts[3])
                p3 = (pts[4], pts[5])
                prev_cubic_ctrl = p2
                prev_quad_ctrl = None
                segments = flatten_cubic_points(p0, p1, p2, p3, tolerance)
                for px, py in segments[1:]:
                    primitives.append(_transform_primitive(LineTo(px, py), self.transform))
                current = p3
            elif op == SMOOTH_CUBIC_TO:
                p0 = current
                reflected = prev_cubic_ctrl
                if reflected is None:
                    reflected = p0
                else:
                    reflected = (2 * p0[0] - reflected[0], 2 * p0[1] - reflected[1])
                p2 = (pts[0], pts[1])
                p3 = (pts[2], pts[3])
                prev_cubic_ctrl = p2
                prev_quad_ctrl = None
                segments = flatten_cubic_points(p0, reflected, p2, p3, tolerance)
                for px, py in segments[1:]:
                    primitives.append(_transform_primitive(LineTo(px, py), self.transform))
                current = p3
            elif op == QUAD_TO:
                p0 = current
                p1 = (pts[0], pts[1])
                p2 = (pts[2], pts[3])
                prev_quad_ctrl = p1
                prev_cubic_ctrl = None
                segments = flatten_quadratic_points(p0, p1, p2, tolerance)
                for px, py in segments[1:]:
                    primitives.append(_transform_primitive(LineTo(px, py), self.transform))
                current = p2
            elif op == SMOOTH_QUAD_TO:
                p0 = current
                reflected = prev_quad_ctrl
                if reflected is None:
                    reflected = p0
                else:
                    reflected = (2 * p0[0] - reflected[0], 2 * p0[1] - reflected[1])
                p2 = (pts[0], pts[1])
                prev_quad_ctrl = reflected
                prev_cubic_ctrl = None
                segments = flatten_quadratic_points(p0, reflected, p2, tolerance)
                for px, py in segments[1:]:
                    primitives.append(_transform_primitive(LineTo(px, py), self.transform))
                current = p2
            elif op == ARC_TO:
                rx, ry, rotation, large, sweep, x, y = pts
                arc_segments = _arc_to_cubic_segments(current, (rx, ry, rotation, large, sweep, x, y))
                prev_cubic_ctrl = None
                prev_quad_ctrl = None
                for seg in arc_segments:
                    segments = flatten_cubic_points(seg[0], seg[1], seg[2], seg[3], tolerance)
                    for px, py in segments[1:]:
                        primitives.append(_transform_primitive(LineTo(px, py), self.transform))
                current = (x, y)
            elif op == CLOSE:
                primitives.append(ClosePath())
                current = start
                prev_cubic_ctrl = None
                prev_quad_ctrl = None
            else:
                primitives.append(cmd)

        return tuple(primitives)


def normalize_path(path_data: str | None, transform: Matrix, stroke_width: float | None) -> NormalizedPath:
    commands = tuple(_parse_path_data(path_data))
    return NormalizedPath(commands=commands, transform=transform, stroke_width=stroke_width)


# Parsing helpers -----------------------------------------------------------------

def _parse_path_data(path_data: str | None) -> Iterable[PathCommand]:
    if not path_data:
        return []

    try:
        tokens = _tokenize(path_data)
    except PathParseError:
        return []

    commands: list[PathCommand] = []
    current = (0.0, 0.0)
    start = (0.0, 0.0)
    prev_command: str | None = None
    prev_ctrl: Point | None = None

    index = 0
    command_token: str | None = None
    while index < len(tokens):
        token = tokens[index]
        if isinstance(token, str):
            command_token = token
            index += 1
        elif command_token is None:
            index += 1
            continue

        if command_token is None:
            break

        absolute = command_token.isupper()
        command = command_token.upper()

        if command == CLOSE:
            commands.append(PathCommand(CLOSE, ()))
            current = start
            prev_ctrl = None
            prev_command = CLOSE
            continue

        numbers, index = _collect_command_numbers(tokens, index)
        idx = 0
        while idx < len(numbers):
            if command == MOVE_TO:
                if idx + 2 > len(numbers):
                    break
                x, y = numbers[idx], numbers[idx + 1]
                idx += 2
                if not absolute:
                    x += current[0]
                    y += current[1]
                current = (x, y)
                start = current
                commands.append(PathCommand(MOVE_TO, (x, y)))
                prev_ctrl = None
                # SVG spec: subsequent coordinate pairs after M are implicit LineTo
                command = LINE_TO
                command_token = LINE_TO if absolute else LINE_TO.lower()
            elif command == LINE_TO:
                if idx + 2 > len(numbers):
                    break
                x, y = numbers[idx], numbers[idx + 1]
                idx += 2
                if not absolute:
                    x += current[0]
                    y += current[1]
                current = (x, y)
                commands.append(PathCommand(LINE_TO, (x, y)))
                prev_ctrl = None
            elif command == H_LINE_TO:
                x = numbers[idx]
                idx += 1
                if not absolute:
                    x += current[0]
                current = (x, current[1])
                commands.append(PathCommand(LINE_TO, (current[0], current[1])))
                prev_ctrl = None
            elif command == V_LINE_TO:
                y = numbers[idx]
                idx += 1
                if not absolute:
                    y += current[1]
                current = (current[0], y)
                commands.append(PathCommand(LINE_TO, (current[0], current[1])))
                prev_ctrl = None
            elif command == CUBIC_TO:
                if idx + 6 > len(numbers):
                    break
                x1, y1, x2, y2, x, y = numbers[idx : idx + 6]
                idx += 6
                if not absolute:
                    x1 += current[0]
                    y1 += current[1]
                    x2 += current[0]
                    y2 += current[1]
                    x += current[0]
                    y += current[1]
                commands.append(PathCommand(CUBIC_TO, (x1, y1, x2, y2, x, y)))
                prev_ctrl = (x2, y2)
                current = (x, y)
            elif command == SMOOTH_CUBIC_TO:
                if idx + 4 > len(numbers):
                    break
                x2, y2, x, y = numbers[idx : idx + 4]
                idx += 4
                if not absolute:
                    x2 += current[0]
                    y2 += current[1]
                    x += current[0]
                    y += current[1]
                if prev_command in {CUBIC_TO, SMOOTH_CUBIC_TO} and prev_ctrl is not None:
                    reflected = (2 * current[0] - prev_ctrl[0], 2 * current[1] - prev_ctrl[1])
                else:
                    reflected = current
                commands.append(PathCommand(CUBIC_TO, (reflected[0], reflected[1], x2, y2, x, y)))
                prev_ctrl = (x2, y2)
                current = (x, y)
            elif command == QUAD_TO:
                if idx + 4 > len(numbers):
                    break
                x1, y1, x, y = numbers[idx : idx + 4]
                idx += 4
                if not absolute:
                    x1 += current[0]
                    y1 += current[1]
                    x += current[0]
                    y += current[1]
                commands.append(PathCommand(QUAD_TO, (x1, y1, x, y)))
                prev_ctrl = (x1, y1)
                current = (x, y)
            elif command == SMOOTH_QUAD_TO:
                if idx + 2 > len(numbers):
                    break
                x, y = numbers[idx : idx + 2]
                idx += 2
                if not absolute:
                    x += current[0]
                    y += current[1]
                if prev_command in {QUAD_TO, SMOOTH_QUAD_TO} and prev_ctrl is not None:
                    ctrl = (2 * current[0] - prev_ctrl[0], 2 * current[1] - prev_ctrl[1])
                else:
                    ctrl = current
                commands.append(PathCommand(SMOOTH_QUAD_TO, (x, y)))
                prev_ctrl = ctrl
                current = (x, y)
            elif command == ARC_TO:
                if idx + 7 > len(numbers):
                    break
                rx, ry, rot, large, sweep, x, y = numbers[idx : idx + 7]
                idx += 7
                if not absolute:
                    x += current[0]
                    y += current[1]
                commands.append(PathCommand(ARC_TO, (rx, ry, rot, bool(int(large)), bool(int(sweep)), x, y)))
                prev_ctrl = None
                current = (x, y)
            else:
                idx = len(numbers)

            prev_command = command

    return commands


def _collect_command_numbers(tokens: list[Token], index: int) -> tuple[list[float], int]:
    numbers: list[float] = []
    while index < len(tokens):
        token = tokens[index]
        if isinstance(token, str):
            break
        numbers.append(token)
        index += 1
    return numbers, index


def _transform_primitive(primitive: object, matrix: Matrix) -> object:
    if isinstance(primitive, MoveTo):
        x, y = apply_matrix_to_xy(primitive.x, primitive.y, matrix)
        return MoveTo(x, y)
    if isinstance(primitive, LineTo):
        x, y = apply_matrix_to_xy(primitive.x, primitive.y, matrix)
        return LineTo(x, y)
    return primitive


# Geometry helpers ----------------------------------------------------------------

def _arc_to_cubic_segments(current: Point, arc: tuple[float, float, float, bool, bool, float, float]) -> list[tuple[Point, Point, Point, Point]]:
    rx, ry, rotation, large, sweep, x, y = arc
    arc_segments = approximate_arc(
        IRPoint(*current),
        IRPoint(x, y),
        rx,
        ry,
        rotation,
        float(bool(large)),
        float(bool(sweep)),
    )
    result: list[tuple[Point, Point, Point, Point]] = []
    for segment in arc_segments:
        if isinstance(segment, BezierSegment):
            result.append(
                (
                    (segment.start.x, segment.start.y),
                    (segment.control1.x, segment.control1.y),
                    (segment.control2.x, segment.control2.y),
                    (segment.end.x, segment.end.y),
                )
            )
        elif isinstance(segment, LineSegment):
            result.append(
                (
                    (segment.start.x, segment.start.y),
                    (segment.start.x, segment.start.y),
                    (segment.end.x, segment.end.y),
                    (segment.end.x, segment.end.y),
                )
            )
    return result
