"""SVG path data parser producing IR geometry segments."""

from __future__ import annotations

import re
import math
from typing import Iterable, Iterator, List

from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType

_COMMAND_RE = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]")
_TOKEN_RE = re.compile(
    r"([MmLlHhVvCcSsQqTtAaZz])|([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)"
)


class PathParseError(ValueError):
    """Raised when path data contains unsupported commands or malformed numbers."""


def parse_path_data(data: str) -> list[SegmentType]:
    """Parse SVG path ``d`` strings into IR segments."""
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
            cursor, last_cubic_control, index = _parse_cubic(
                tokens, index, command, cursor, segments
            )
            last_quadratic_control = None
        elif command in {"S", "s"}:
            cursor, last_cubic_control, index = _parse_smooth_cubic(
                tokens, index, command, cursor, segments, last_cubic_control
            )
            last_quadratic_control = None
        elif command in {"Q", "q"}:
            cursor, last_quadratic_control, index = _parse_quadratic(
                tokens, index, command, cursor, segments
            )
            last_cubic_control = None
        elif command in {"T", "t"}:
            cursor, last_quadratic_control, index = _parse_smooth_quadratic(
                tokens, index, command, cursor, segments, last_quadratic_control
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

    return segments


def _tokenize(data: str) -> list[str | float]:
    matches = _TOKEN_RE.findall(data)
    tokens: list[str | float] = []
    for cmd, number in matches:
        if cmd:
            tokens.append(cmd)
        elif number:
            tokens.append(float(number))
    return tokens


def _parse_moveto(
    tokens: list[str | float],
    index: int,
    command: str,
    cursor: Point,
    segments: List[SegmentType],
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
    tokens: list[str | float],
    index: int,
    command: str,
    cursor: Point,
    segments: List[SegmentType],
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


def _parse_smooth_cubic(
    tokens: list[str | float],
    index: int,
    command: str,
    cursor: Point,
    segments: List[SegmentType],
    last_cubic_control: Point | None,
) -> tuple[Point, Point | None, int]:
    is_relative = command == "s"
    numbers, index = _take_numbers(tokens, index, 4, allow_multiple=True)
    if len(numbers) % 4 != 0:
        raise PathParseError("smooth cubic curve requires sets of four numbers")

    for i in range(0, len(numbers), 4):
        x1, y1, x, y = numbers[i : i + 4]
        control1 = (
            Point(
                2 * cursor.x - last_cubic_control.x,
                2 * cursor.y - last_cubic_control.y,
            )
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
    tokens: list[str | float],
    index: int,
    command: str,
    cursor: Point,
    segments: List[SegmentType],
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
        cubic1 = Point(
            cursor.x + (2.0 / 3.0) * (control.x - cursor.x),
            cursor.y + (2.0 / 3.0) * (control.y - cursor.y),
        )
        cubic2 = Point(
            target.x + (2.0 / 3.0) * (control.x - target.x),
            target.y + (2.0 / 3.0) * (control.y - target.y),
        )
        segments.append(BezierSegment(cursor, cubic1, cubic2, target))
        cursor = target
        last_control = control
    return cursor, last_control, index


def _parse_smooth_quadratic(
    tokens: list[str | float],
    index: int,
    command: str,
    cursor: Point,
    segments: List[SegmentType],
    last_quadratic_control: Point | None,
) -> tuple[Point, Point | None, int]:
    is_relative = command == "t"
    numbers, index = _take_numbers(tokens, index, 2, allow_multiple=True)
    if len(numbers) % 2 != 0:
        raise PathParseError("smooth quadratic curve requires coordinate pairs")

    for i in range(0, len(numbers), 2):
        x, y = numbers[i : i + 2]
        if last_quadratic_control is not None:
            control = Point(
                2 * cursor.x - last_quadratic_control.x,
                2 * cursor.y - last_quadratic_control.y,
            )
        else:
            control = cursor
        target = _resolve_relative_point(cursor, x, y, is_relative)
        cubic1 = Point(
            cursor.x + (2.0 / 3.0) * (control.x - cursor.x),
            cursor.y + (2.0 / 3.0) * (control.y - cursor.y),
        )
        cubic2 = Point(
            target.x + (2.0 / 3.0) * (control.x - target.x),
            target.y + (2.0 / 3.0) * (control.y - target.y),
        )
        segments.append(BezierSegment(cursor, cubic1, cubic2, target))
        cursor = target
        last_quadratic_control = control
    return cursor, last_quadratic_control, index


def _parse_horizontal(
    tokens: list[str | float],
    index: int,
    command: str,
    cursor: Point,
    segments: List[SegmentType],
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
    tokens: list[str | float],
    index: int,
    command: str,
    cursor: Point,
    segments: List[SegmentType],
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
    tokens: list[str | float],
    index: int,
    command: str,
    cursor: Point,
    segments: List[SegmentType],
) -> tuple[Point, Point, int]:
    is_relative = command == "c"
    numbers, index = _take_numbers(tokens, index, 6, allow_multiple=True)
    if len(numbers) % 6 != 0:
        raise PathParseError("cubic curve requires sets of six numbers")

    last_control = cursor
    for i in range(0, len(numbers), 6):
        x1, y1, x2, y2, x, y = numbers[i : i + 6]
        if is_relative:
            control1 = Point(cursor.x + x1, cursor.y + y1)
            control2 = Point(cursor.x + x2, cursor.y + y2)
            target = Point(cursor.x + x, cursor.y + y)
        else:
            control1 = Point(x1, y1)
            control2 = Point(x2, y2)
            target = Point(x, y)
        segments.append(BezierSegment(cursor, control1, control2, target))
        cursor = target
        last_control = control2
    return cursor, last_control, index


def _parse_arc(
    tokens: list[str | float],
    index: int,
    command: str,
    cursor: Point,
    segments: List[SegmentType],
) -> tuple[Point, int]:
    is_relative = command == "a"
    numbers, index = _take_numbers(tokens, index, 7, allow_multiple=True)
    if len(numbers) % 7 != 0:
        raise PathParseError("arc command requires sets of seven numbers")

    for i in range(0, len(numbers), 7):
        rx, ry, rotation, large_arc, sweep, x, y = numbers[i : i + 7]
        target = Point(cursor.x + x, cursor.y + y) if is_relative else Point(x, y)
        segments.extend(_arc_to_beziers(cursor, target, rx, ry, rotation, bool(large_arc), bool(sweep)))
        cursor = target
    return cursor, index


def _take_numbers(
    tokens: list[str | float],
    index: int,
    minimum: int,
    *,
    allow_multiple: bool,
) -> tuple[list[float], int]:
    numbers: list[float] = []
    length = len(tokens)
    while index < length:
        value = tokens[index]
        if isinstance(value, str):
            break
        numbers.append(float(value))
        index += 1
        if not allow_multiple and len(numbers) >= minimum:
            break
    if len(numbers) < minimum:
        raise PathParseError("insufficient numeric values for command")
    return numbers, index


def _arc_to_beziers(
    start: Point,
    end: Point,
    rx: float,
    ry: float,
    x_axis_rotation: float,
    large_arc: bool,
    sweep: bool,
) -> list[SegmentType]:
    import math

    if rx == 0 or ry == 0 or (start.x == end.x and start.y == end.y):
        return [LineSegment(start, end)]

    phi = math.radians(x_axis_rotation % 360.0)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)

    dx = (start.x - end.x) / 2.0
    dy = (start.y - end.y) / 2.0
    x1_prime = cos_phi * dx + sin_phi * dy
    y1_prime = -sin_phi * dx + cos_phi * dy

    rx_abs = abs(rx)
    ry_abs = abs(ry)
    radius_check = (x1_prime ** 2) / (rx_abs ** 2) + (y1_prime ** 2) / (ry_abs ** 2)
    if radius_check > 1:
        scale = math.sqrt(radius_check)
        rx_abs *= scale
        ry_abs *= scale

    sign = -1 if large_arc == sweep else 1
    numerator = (rx_abs ** 2) * (ry_abs ** 2) - (rx_abs ** 2) * (y1_prime ** 2) - (ry_abs ** 2) * (x1_prime ** 2)
    denominator = (rx_abs ** 2) * (y1_prime ** 2) + (ry_abs ** 2) * (x1_prime ** 2)
    denominator = max(denominator, 1e-12)
    coef = sign * math.sqrt(max(numerator / denominator, 0.0))
    cx_prime = coef * (rx_abs * y1_prime) / ry_abs
    cy_prime = coef * (-ry_abs * x1_prime) / rx_abs

    cx = cos_phi * cx_prime - sin_phi * cy_prime + (start.x + end.x) / 2.0
    cy = sin_phi * cx_prime + cos_phi * cy_prime + (start.y + end.y) / 2.0

    def _angle(u: tuple[float, float], v: tuple[float, float]) -> float:
        dot = u[0] * v[0] + u[1] * v[1]
        det = u[0] * v[1] - u[1] * v[0]
        return math.atan2(det, dot)

    start_vector = ((x1_prime - cx_prime) / rx_abs, (y1_prime - cy_prime) / ry_abs)
    end_vector = ((-x1_prime - cx_prime) / rx_abs, (-y1_prime - cy_prime) / ry_abs)

    theta1 = _angle((1.0, 0.0), start_vector)
    delta_theta = _angle(start_vector, end_vector)
    if not sweep and delta_theta > 0:
        delta_theta -= 2 * math.pi
    elif sweep and delta_theta < 0:
        delta_theta += 2 * math.pi

    segments: list[SegmentType] = []
    segment_count = max(int(math.ceil(abs(delta_theta) / (math.pi / 2.0))), 1)
    delta = delta_theta / segment_count

    for i in range(segment_count):
        t1 = theta1 + i * delta
        t2 = t1 + delta

        sin_t1 = math.sin(t1)
        cos_t1 = math.cos(t1)
        sin_t2 = math.sin(t2)
        cos_t2 = math.cos(t2)

        e1 = Point(
            cx + rx_abs * (cos_phi * cos_t1 - sin_phi * sin_t1),
            cy + ry_abs * (sin_phi * cos_t1 + cos_phi * sin_t1),
        )
        e2 = Point(
            cx + rx_abs * (cos_phi * cos_t2 - sin_phi * sin_t2),
            cy + ry_abs * (sin_phi * cos_t2 + cos_phi * sin_t2),
        )

        alpha = math.tan(delta / 4.0) * 4.0 / 3.0
        control1 = Point(
            e1.x - alpha * (rx_abs * (cos_phi * sin_t1 + sin_phi * cos_t1)),
            e1.y - alpha * (ry_abs * (sin_phi * sin_t1 - cos_phi * cos_t1)),
        )
        control2 = Point(
            e2.x + alpha * (rx_abs * (cos_phi * sin_t2 + sin_phi * cos_t2)),
            e2.y + alpha * (ry_abs * (sin_phi * sin_t2 - cos_phi * cos_t2)),
        )

        start_point = start if i == 0 else segments[-1].end  # type: ignore[attr-defined]
        segments.append(BezierSegment(start_point, control1, control2, e2))

    segments[0] = BezierSegment(start, segments[0].control1, segments[0].control2, segments[0].end)
    return segments


def _resolve_relative_point(cursor: Point, x: float, y: float, is_relative: bool) -> Point:
    if is_relative:
        return Point(cursor.x + x, cursor.y + y)
    return Point(x, y)


__all__ = ["parse_path_data", "PathParseError"]
