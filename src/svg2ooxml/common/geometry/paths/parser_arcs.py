"""SVG elliptical arc parsing and cubic approximation."""

from __future__ import annotations

import math

from svg2ooxml.common.geometry.paths.parser_geometry import _resolve_relative_point
from svg2ooxml.common.geometry.paths.parser_tokens import _take_numbers
from svg2ooxml.common.geometry.paths.parser_types import PathParseError, Token
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType


def _parse_arc(
    tokens: list[Token],
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
        arc_segments = _approximate_arc(
            cursor,
            target,
            rx,
            ry,
            x_axis_rotation,
            large_arc_flag,
            sweep_flag,
        )
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
    return approximate_arc(
        start,
        end,
        rx,
        ry,
        x_axis_rotation,
        large_arc_flag,
        sweep_flag,
    )


def approximate_arc(
    start: Point,
    end: Point,
    rx: float,
    ry: float,
    x_axis_rotation: float,
    large_arc_flag: float,
    sweep_flag: float,
) -> list[SegmentType]:
    """Approximate one SVG elliptical arc command as IR path segments."""

    if rx == 0 or ry == 0:
        return [LineSegment(start, end)]

    arc = _arc_to_center_parameters(
        start,
        end,
        rx,
        ry,
        x_axis_rotation,
        large_arc_flag,
        sweep_flag,
    )
    return _arc_to_bezier_segments(*arc)


def _arc_to_center_parameters(
    start: Point,
    end: Point,
    rx: float,
    ry: float,
    x_axis_rotation: float,
    large_arc_flag: float,
    sweep_flag: float,
) -> tuple[Point, float, float, float, float, float]:
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
    center_factor = 0 if denominator == 0 else sign * math.sqrt(max(0, numerator / denominator))

    cx_prime = center_factor * (rx * y1_prime) / ry
    cy_prime = -center_factor * (ry * x1_prime) / rx

    cx = math.cos(phi) * cx_prime - math.sin(phi) * cy_prime + (start.x + end.x) / 2.0
    cy = math.sin(phi) * cx_prime + math.cos(phi) * cy_prime + (start.y + end.y) / 2.0

    ux = (x1_prime - cx_prime) / rx
    uy = (y1_prime - cy_prime) / ry
    vx = (-x1_prime - cx_prime) / rx
    vy = (-y1_prime - cy_prime) / ry

    start_angle = _arc_angle(1.0, 0.0, ux, uy) % 360.0
    delta_angle = _arc_angle(ux, uy, vx, vy) % 360.0
    if sweep_flag == 0 and delta_angle > 0:
        delta_angle -= 360.0
    elif sweep_flag == 1 and delta_angle < 0:
        delta_angle += 360.0

    return Point(cx, cy), rx, ry, phi, start_angle, delta_angle


def _arc_angle(u_x: float, u_y: float, v_x: float, v_y: float) -> float:
    dot = u_x * v_x + u_y * v_y
    det = u_x * v_y - u_y * v_x
    return math.degrees(math.atan2(det, dot))


def _arc_to_bezier_segments(
    center: Point,
    rx: float,
    ry: float,
    phi: float,
    start_angle: float,
    sweep_angle: float,
) -> list[SegmentType]:
    if sweep_angle == 0:
        return []

    segment_count = max(int(math.ceil(abs(sweep_angle) / 90.0)), 1)
    angle_increment = math.radians(sweep_angle / segment_count)
    current_angle = math.radians(start_angle)

    output: list[SegmentType] = []
    start_point = _arc_point(center, rx, ry, phi, current_angle)

    for _ in range(segment_count):
        end_angle = current_angle + angle_increment
        end_point = _arc_point(center, rx, ry, phi, end_angle)
        alpha = math.tan(angle_increment / 4.0) * 4.0 / 3.0

        start_tangent = _arc_derivative(rx, ry, phi, current_angle)
        end_tangent = _arc_derivative(rx, ry, phi, end_angle)
        control1 = Point(
            start_point.x + alpha * start_tangent.x,
            start_point.y + alpha * start_tangent.y,
        )
        control2 = Point(
            end_point.x - alpha * end_tangent.x,
            end_point.y - alpha * end_tangent.y,
        )

        output.append(BezierSegment(start_point, control1, control2, end_point))
        start_point = end_point
        current_angle = end_angle

    return output


def _arc_point(center: Point, rx: float, ry: float, phi: float, theta: float) -> Point:
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)
    x = rx * math.cos(theta)
    y = ry * math.sin(theta)
    return Point(
        center.x + cos_phi * x - sin_phi * y,
        center.y + sin_phi * x + cos_phi * y,
    )


def _arc_derivative(rx: float, ry: float, phi: float, theta: float) -> Point:
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)
    dx = -rx * math.sin(theta)
    dy = ry * math.cos(theta)
    return Point(
        cos_phi * dx - sin_phi * dy,
        sin_phi * dx + cos_phi * dy,
    )


__all__ = ["_parse_arc", "approximate_arc"]
