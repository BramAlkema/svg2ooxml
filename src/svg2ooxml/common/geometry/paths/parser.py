"""SVG path data parser producing IR geometry segments."""

from __future__ import annotations

import math
import re

from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType

_COMMAND_RE = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]")
_TOKEN_RE = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")


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
            cursor, last_cubic_control, index = _parse_cubic(tokens, index, command, cursor, segments)
            last_quadratic_control = None
        elif command in {"S", "s"}:
            cursor, last_cubic_control, index = _parse_smooth_cubic(
                tokens, index, command, cursor, segments, last_cubic_control
            )
            last_quadratic_control = None
        elif command in {"Q", "q"}:
            cursor, last_quadratic_control, index = _parse_quadratic(tokens, index, command, cursor, segments)
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
    tokens: list[str | float],
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


def _parse_smooth_cubic(
    tokens: list[str | float],
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
    tokens: list[str | float],
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
        segments.append(_quadratic_to_cubic(cursor, control, target))
        cursor = target
        last_control = control
    return cursor, last_control, index


def _parse_smooth_quadratic(
    tokens: list[str | float],
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
        segments.append(_quadratic_to_cubic(cursor, control, target))
        cursor = target
        last_quadratic_control = control
    return cursor, last_quadratic_control, index


def _parse_cubic(
    tokens: list[str | float],
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


def _parse_horizontal(
    tokens: list[str | float],
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
    tokens: list[str | float],
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


def _parse_arc(
    tokens: list[str | float],
    index: int,
    command: str,
    cursor: Point,
    segments: list[SegmentType],
) -> tuple[Point, int]:
    is_relative = command == "a"
    numbers, index = _take_numbers(tokens, index, 7, allow_multiple=True)
    if len(numbers) % 7 != 0:
        raise PathParseError("arc requires sets of seven numbers")

    for i in range(0, len(numbers), 7):
        rx, ry, x_axis_rotation, large_arc_flag, sweep_flag, x, y = numbers[i : i + 7]
        target = _resolve_relative_point(cursor, x, y, is_relative)
        arc_segments = _approximate_arc(cursor, target, rx, ry, x_axis_rotation, large_arc_flag, sweep_flag)
        segments.extend(arc_segments)
        cursor = target
    return cursor, index


def _approximate_arc(
    start: Point,
    end: Point,
    rx: float,
    ry: float,
    x_axis_rotation: float,
    large_arc_flag: float,
    sweep_flag: float,
) -> list[SegmentType]:
    if rx == 0 or ry == 0:
        return [LineSegment(start, end)]

    arc = _arc_to_center_parameters(start, end, rx, ry, x_axis_rotation, large_arc_flag, sweep_flag)
    return _arc_to_bezier_segments(*arc)


def _arc_to_center_parameters(
    start: Point,
    end: Point,
    rx: float,
    ry: float,
    x_axis_rotation: float,
    large_arc_flag: float,
    sweep_flag: float,
) -> tuple[Point, float, float, float, float]:
    phi = math.radians(x_axis_rotation % 360.0)

    dx = (start.x - end.x) / 2.0
    dy = (start.y - end.y) / 2.0

    x1_prime = math.cos(phi) * dx + math.sin(phi) * dy
    y1_prime = -math.sin(phi) * dx + math.cos(phi) * dy

    rx = abs(rx)
    ry = abs(ry)
    rx_sq = rx * rx
    ry_sq = ry * ry
    x1_prime_sq = x1_prime * x1_prime
    y1_prime_sq = y1_prime * y1_prime

    radii_check = x1_prime_sq / rx_sq + y1_prime_sq / ry_sq
    if radii_check > 1:
        scale = math.sqrt(radii_check)
        rx *= scale
        ry *= scale
        rx_sq = rx * rx
        ry_sq = ry * ry

    sign = -1 if large_arc_flag == sweep_flag else 1
    numerator = rx_sq * ry_sq - rx_sq * y1_prime_sq - ry_sq * x1_prime_sq
    denominator = rx_sq * y1_prime_sq + ry_sq * x1_prime_sq
    if denominator == 0:
        center_factor = 0
    else:
        center_factor = sign * math.sqrt(max(0, numerator / denominator))

    cx_prime = center_factor * (rx * y1_prime) / ry
    cy_prime = -center_factor * (ry * x1_prime) / rx

    cx = math.cos(phi) * cx_prime - math.sin(phi) * cy_prime + (start.x + end.x) / 2.0
    cy = math.sin(phi) * cx_prime + math.cos(phi) * cy_prime + (start.y + end.y) / 2.0

    ux = (x1_prime - cx_prime) / rx
    uy = (y1_prime - cy_prime) / ry
    vx = (-x1_prime - cx_prime) / rx
    vy = (-y1_prime - cy_prime) / ry

    def _angle(u_x: float, u_y: float, v_x: float, v_y: float) -> float:
        dot = u_x * v_x + u_y * v_y
        det = u_x * v_y - u_y * v_x
        angle = math.degrees(math.atan2(det, dot))
        return angle

    start_angle = _angle(1.0, 0.0, ux, uy) % 360.0
    delta_angle = _angle(ux, uy, vx, vy) % 360.0
    if sweep_flag == 0 and delta_angle > 0:
        delta_angle -= 360.0
    elif sweep_flag == 1 and delta_angle < 0:
        delta_angle += 360.0

    return Point(cx, cy), rx, ry, start_angle, delta_angle


def _arc_to_bezier_segments(
    center: Point,
    rx: float,
    ry: float,
    start_angle: float,
    sweep_angle: float,
) -> list[SegmentType]:
    if sweep_angle == 0:
        return []

    segments = max(int(math.ceil(abs(sweep_angle) / 90.0)), 1)
    angle_increment = sweep_angle / segments
    current_angle = math.radians(start_angle)

    output: list[SegmentType] = []
    start_point = Point(
        center.x + rx * math.cos(current_angle),
        center.y + ry * math.sin(current_angle),
    )

    for _ in range(segments):
        current_angle += math.radians(angle_increment)
        end_point = Point(
            center.x + rx * math.cos(current_angle),
            center.y + ry * math.sin(current_angle),
        )
        alpha = math.tan(math.radians(angle_increment) / 4.0) * 4.0 / 3.0

        control1 = Point(
            start_point.x - alpha * rx * math.sin(math.radians(start_angle)),
            start_point.y + alpha * ry * math.cos(math.radians(start_angle)),
        )
        control2 = Point(
            end_point.x + alpha * rx * math.sin(math.radians(start_angle + sweep_angle)),
            end_point.y - alpha * ry * math.cos(math.radians(start_angle + sweep_angle)),
        )

        output.append(BezierSegment(start_point, control1, control2, end_point))
        start_point = end_point
        start_angle += angle_increment

    return output


def _take_numbers(
    tokens: list[str | float],
    index: int,
    required: int,
    *,
    allow_multiple: bool = False,
) -> tuple[list[float], int]:
    numbers: list[float] = []
    while index < len(tokens):
        token = tokens[index]
        if isinstance(token, str) and _COMMAND_RE.match(token):
            break
        if not isinstance(token, float):
            raise PathParseError(f"Expected number, got {token!r}")
        numbers.append(token)
        index += 1
        if not allow_multiple and len(numbers) >= required:
            break
    if len(numbers) < required:
        raise PathParseError("Insufficient numeric values for command")
    return numbers, index


def _resolve_relative_point(base: Point, x: float, y: float, is_relative: bool) -> Point:
    return Point(base.x + x, base.y + y) if is_relative else Point(x, y)


def _quadratic_to_cubic(start: Point, control: Point, end: Point) -> BezierSegment:
    control1 = Point(start.x + (2.0 / 3.0) * (control.x - start.x), start.y + (2.0 / 3.0) * (control.y - start.y))
    control2 = Point(end.x + (2.0 / 3.0) * (control.x - end.x), end.y + (2.0 / 3.0) * (control.y - end.y))
    return BezierSegment(start, control1, control2, end)


__all__ = ["PathParseError", "parse_path_data"]
