"""Normalize SVG path data into absolute commands and flattened primitives."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from .matrix import Matrix
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
                primitives.append(_transform_point(MoveTo(*current), self.transform))
            elif op == LINE_TO:
                current = (pts[0], pts[1])
                prev_cubic_ctrl = None
                prev_quad_ctrl = None
                primitives.append(_transform_point(LineTo(*current), self.transform))
            elif op == CUBIC_TO:
                p0 = current
                p1 = (pts[0], pts[1])
                p2 = (pts[2], pts[3])
                p3 = (pts[4], pts[5])
                prev_cubic_ctrl = p2
                prev_quad_ctrl = None
                segments = _flatten_cubic(p0, p1, p2, p3, tolerance)
                for px, py in segments[1:]:
                    primitives.append(_transform_point(LineTo(px, py), self.transform))
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
                segments = _flatten_cubic(p0, reflected, p2, p3, tolerance)
                for px, py in segments[1:]:
                    primitives.append(_transform_point(LineTo(px, py), self.transform))
                current = p3
            elif op == QUAD_TO:
                p0 = current
                p1 = (pts[0], pts[1])
                p2 = (pts[2], pts[3])
                prev_quad_ctrl = p1
                prev_cubic_ctrl = None
                segments = _flatten_quadratic(p0, p1, p2, tolerance)
                for px, py in segments[1:]:
                    primitives.append(_transform_point(LineTo(px, py), self.transform))
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
                segments = _flatten_quadratic(p0, reflected, p2, tolerance)
                for px, py in segments[1:]:
                    primitives.append(_transform_point(LineTo(px, py), self.transform))
                current = p2
            elif op == ARC_TO:
                rx, ry, rotation, large, sweep, x, y = pts
                arc_segments = _arc_to_cubic_segments(current, (rx, ry, rotation, large, sweep, x, y))
                prev_cubic_ctrl = None
                prev_quad_ctrl = None
                for seg in arc_segments:
                    segments = _flatten_cubic(seg[0], seg[1], seg[2], seg[3], tolerance)
                    for px, py in segments[1:]:
                        primitives.append(_transform_point(LineTo(px, py), self.transform))
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

    tokens = _tokenize_path(path_data)
    commands: list[PathCommand] = []
    current = (0.0, 0.0)
    start = (0.0, 0.0)
    prev_command: str | None = None
    prev_ctrl: Point | None = None

    iterator = iter(tokens)
    for token in iterator:
        if token.upper() not in "MZLHVCSQTA":
            continue
        absolute = token.isupper()
        command = token.upper()

        if command == CLOSE:
            commands.append(PathCommand(CLOSE, ()))
            current = start
            prev_ctrl = None
            prev_command = CLOSE
            continue

        numbers = _read_numbers(next(iterator, ""))
        idx = 0
        while idx < len(numbers):
            if command == MOVE_TO:
                x, y = numbers[idx], numbers[idx + 1]
                idx += 2
                if not absolute:
                    x += current[0]
                    y += current[1]
                current = (x, y)
                start = current
                commands.append(PathCommand(MOVE_TO if not commands else LINE_TO, (x, y)))
                prev_ctrl = None
            elif command == LINE_TO:
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


def _tokenize_path(data: str) -> list[str]:
    tokens: list[str] = []
    buffer = ""
    for char in data:
        if char in "MmZzLlHhVvCcSsQqTtAa":
            if buffer.strip():
                tokens.append(buffer.strip())
            tokens.append(char)
            buffer = ""
        else:
            buffer += char
    if buffer.strip():
        tokens.append(buffer.strip())
    return tokens


def _read_numbers(chunk: str) -> list[float]:
    if not chunk:
        return []
    normalized = chunk.replace("e-", "E-").replace("e+", "E+")
    parts: list[str] = []
    current = ""
    for _idx, char in enumerate(normalized):
        if char in ", ":
            if current:
                parts.append(current)
                current = ""
        elif char in "+-" and current and current[-1] not in "Ee":
            parts.append(current)
            current = char
        else:
            current += char
    if current:
        parts.append(current)
    result: list[float] = []
    for part in parts:
        if part in {"+", "-"}:
            continue
        try:
            result.append(float(part))
        except ValueError:
            pass
    return result


def _transform_point(primitive: object, matrix: Matrix) -> object:
    if isinstance(primitive, MoveTo):
        x, y = matrix.apply_to_point(primitive.x, primitive.y)
        return MoveTo(x, y)
    if isinstance(primitive, LineTo):
        x, y = matrix.apply_to_point(primitive.x, primitive.y)
        return LineTo(x, y)
    return primitive


# Geometry helpers ----------------------------------------------------------------

def _flatten_cubic(p0: Point, p1: Point, p2: Point, p3: Point, tolerance: float) -> list[Point]:
    def recursive(a: Point, b: Point, c: Point, d: Point) -> list[Point]:
        max_dist = max(
            _distance_point_to_line(b, a, d),
            _distance_point_to_line(c, a, d),
        )
        if max_dist <= tolerance:
            return [a, d]
        ab = _midpoint(a, b)
        bc = _midpoint(b, c)
        cd = _midpoint(c, d)
        abc = _midpoint(ab, bc)
        bcd = _midpoint(bc, cd)
        abcd = _midpoint(abc, bcd)
        left = recursive(a, ab, abc, abcd)
        right = recursive(abcd, bcd, cd, d)
        return left[:-1] + right

    return recursive(p0, p1, p2, p3)


def _flatten_quadratic(p0: Point, p1: Point, p2: Point, tolerance: float) -> list[Point]:
    c1 = (p0[0] + 2.0 / 3.0 * (p1[0] - p0[0]), p0[1] + 2.0 / 3.0 * (p1[1] - p0[1]))
    c2 = (p2[0] + 2.0 / 3.0 * (p1[0] - p2[0]), p2[1] + 2.0 / 3.0 * (p1[1] - p2[1]))
    return _flatten_cubic(p0, c1, c2, p2, tolerance)


def _arc_to_cubic_segments(current: Point, arc: tuple[float, float, float, bool, bool, float, float]) -> list[tuple[Point, Point, Point, Point]]:
    rx, ry, rotation, large, sweep, x, y = arc
    if rx == 0 or ry == 0:
        return [(current, current, (x, y), (x, y))]
    rotation = math.radians(rotation % 360.0)
    cos_rot = math.cos(rotation)
    sin_rot = math.sin(rotation)
    dx2 = (current[0] - x) / 2.0
    dy2 = (current[1] - y) / 2.0
    x1p = cos_rot * dx2 + sin_rot * dy2
    y1p = -sin_rot * dx2 + cos_rot * dy2
    rx_sq = rx * rx
    ry_sq = ry * ry
    x1p_sq = x1p * x1p
    y1p_sq = y1p * y1p
    radicant = max(0.0, (rx_sq * ry_sq - rx_sq * y1p_sq - ry_sq * x1p_sq) / (rx_sq * y1p_sq + ry_sq * x1p_sq))
    coef = math.sqrt(radicant) * (1 if large != sweep else -1)
    cxp = coef * ((rx * y1p) / ry)
    cyp = coef * (-(ry * x1p) / rx)
    cx = cos_rot * cxp - sin_rot * cyp + (current[0] + x) / 2.0
    cy = sin_rot * cxp + cos_rot * cyp + (current[1] + y) / 2.0

    start_angle = _angle((1, 0), ((x1p - cxp) / rx, (y1p - cyp) / ry))
    delta_angle = _angle(((x1p - cxp) / rx, (y1p - cyp) / ry), ((-x1p - cxp) / rx, (-y1p - cyp) / ry))
    if not sweep and delta_angle > 0:
        delta_angle -= 2 * math.pi
    elif sweep and delta_angle < 0:
        delta_angle += 2 * math.pi

    segments = max(int(math.ceil(abs(delta_angle) / (math.pi / 2))), 1)
    delta = delta_angle / segments
    t = 8.0 / 3.0 * math.sin(delta / 4.0) ** 2 / math.sin(delta / 2.0)
    result: list[tuple[Point, Point, Point, Point]] = []
    angle = start_angle
    for _ in range(segments):
        start = angle
        end = angle + delta
        sin_start = math.sin(start)
        cos_start = math.cos(start)
        sin_end = math.sin(end)
        cos_end = math.cos(end)

        p0 = (
            cx + rx * (cos_rot * cos_start - sin_rot * sin_start),
            cy + ry * (sin_rot * cos_start + cos_rot * sin_start),
        )
        p3 = (
            cx + rx * (cos_rot * cos_end - sin_rot * sin_end),
            cy + ry * (sin_rot * cos_end + cos_rot * sin_end),
        )
        dx = -rx * (cos_rot * sin_start + sin_rot * cos_start)
        dy = -ry * (sin_rot * sin_start - cos_rot * cos_start)
        p1 = (p0[0] + dx * t, p0[1] + dy * t)
        dx = -rx * (cos_rot * sin_end + sin_rot * cos_end)
        dy = -ry * (sin_rot * sin_end - cos_rot * cos_end)
        p2 = (p3[0] - dx * t, p3[1] - dy * t)
        result.append((p0, p1, p2, p3))
        angle = end
    return result


def _distance_point_to_line(point: Point, start: Point, end: Point) -> float:
    x0, y0 = point
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x0 - x1, y0 - y1)
    return abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / math.hypot(dx, dy)


def _midpoint(p1: Point, p2: Point) -> Point:
    return ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5)


def _angle(u: Point, v: Point) -> float:
    dot = u[0] * v[0] + u[1] * v[1]
    det = u[0] * v[1] - u[1] * v[0]
    return math.atan2(det, dot)
