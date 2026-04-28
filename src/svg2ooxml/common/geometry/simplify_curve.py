"""Cubic curve fitting for path simplification."""

from __future__ import annotations

from svg2ooxml.common.geometry.points import (
    Vector2,
    dot_vectors,
    normalize_vector,
    point_distance,
    vector_between,
)
from svg2ooxml.common.geometry.simplify_runs import map_line_runs, run_to_points
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType


def curve_fit(
    segments: list[SegmentType],
    tolerance: float,
    min_points: int,
    epsilon: float,
) -> list[SegmentType]:
    """Re-fit long line runs into fewer cubic Bezier segments."""

    def transform(run: list[LineSegment]) -> list[SegmentType]:
        points = run_to_points(run)
        if len(points) < min_points:
            return list(run)
        fitted = fit_cubic_beziers(points, tolerance)
        if _segment_weight(fitted) < len(run):
            return fitted
        return list(run)

    return map_line_runs(segments, epsilon, transform)


def fit_cubic_beziers(
    points: list[Point],
    tolerance: float,
) -> list[BezierSegment]:
    """Fit cubic Bezier curves to a point sequence using Schneider-style splitting."""

    if len(points) < 3:
        return []

    left_tangent = normalize_vector(vector_between(points[1], points[0]))
    right_tangent = normalize_vector(vector_between(points[-2], points[-1]))
    result: list[BezierSegment] = []
    stack: list[tuple[list[Point], Vector2, Vector2]] = [
        (points, left_tangent, right_tangent),
    ]

    while stack:
        current_points, left, right = stack.pop()
        if len(current_points) < 3:
            continue

        parameters = chord_length_parameterize(current_points)
        bezier = fit_single_cubic(current_points, left, right, parameters)
        max_error, split_index = compute_max_error(current_points, bezier, parameters)

        if max_error <= tolerance:
            result.append(bezier)
            continue

        split_index = max(1, min(split_index, len(current_points) - 2))
        center_tangent = normalize_vector(
            vector_between(
                current_points[split_index + 1], current_points[split_index - 1]
            )
        )
        negative_center_tangent = (-center_tangent[0], -center_tangent[1])
        stack.append((current_points[split_index:], center_tangent, right))
        stack.append((current_points[: split_index + 1], left, negative_center_tangent))

    return result


def fit_single_cubic(
    points: list[Point],
    left_tangent: Vector2,
    right_tangent: Vector2,
    parameters: list[float],
) -> BezierSegment:
    """Fit one cubic Bezier segment with least squares."""

    first = points[0]
    last = points[-1]
    a00 = a01 = a11 = 0.0
    x0 = x1 = 0.0

    for index, point in enumerate(points):
        t = parameters[index]
        b1 = 3.0 * t * (1.0 - t) ** 2
        b2 = 3.0 * t**2 * (1.0 - t)
        a1 = (left_tangent[0] * b1, left_tangent[1] * b1)
        a2 = (right_tangent[0] * b2, right_tangent[1] * b2)

        a00 += dot_vectors(a1, a1)
        a01 += dot_vectors(a1, a2)
        a11 += dot_vectors(a2, a2)

        b0 = (1.0 - t) ** 3
        b3 = t**3
        residual = (
            point.x - (first.x * b0 + first.x * b1 + last.x * b2 + last.x * b3),
            point.y - (first.y * b0 + first.y * b1 + last.y * b2 + last.y * b3),
        )
        x0 += dot_vectors(a1, residual)
        x1 += dot_vectors(a2, residual)

    determinant = a00 * a11 - a01 * a01
    if abs(determinant) < 1e-12:
        return _fallback_cubic(first, last, left_tangent, right_tangent)

    alpha_left = (a11 * x0 - a01 * x1) / determinant
    alpha_right = (a00 * x1 - a01 * x0) / determinant
    segment_length = point_distance(first, last)
    epsilon = 1e-6 * segment_length
    if alpha_left < epsilon or alpha_right < epsilon:
        alpha_left = segment_length / 3.0
        alpha_right = segment_length / 3.0

    return _cubic_from_tangents(
        first, last, left_tangent, right_tangent, alpha_left, alpha_right
    )


def compute_max_error(
    points: list[Point],
    bezier: BezierSegment,
    parameters: list[float],
) -> tuple[float, int]:
    """Return max fitting error and the point index where it occurs."""

    max_distance = 0.0
    max_index = 0
    for index in range(1, len(points) - 1):
        fitted_point = eval_bezier(bezier, parameters[index])
        distance = point_distance(points[index], fitted_point)
        if distance > max_distance:
            max_distance = distance
            max_index = index
    return max_distance, max_index


def eval_bezier(bezier: BezierSegment, t: float) -> Point:
    """Evaluate a cubic Bezier at parameter ``t``."""

    mt = 1.0 - t
    mt2 = mt * mt
    t2 = t * t
    return Point(
        mt2 * mt * bezier.start.x
        + 3 * mt2 * t * bezier.control1.x
        + 3 * mt * t2 * bezier.control2.x
        + t2 * t * bezier.end.x,
        mt2 * mt * bezier.start.y
        + 3 * mt2 * t * bezier.control1.y
        + 3 * mt * t2 * bezier.control2.y
        + t2 * t * bezier.end.y,
    )


def chord_length_parameterize(points: list[Point]) -> list[float]:
    """Assign normalized parameters using cumulative chord length."""

    parameters = [0.0]
    for index in range(1, len(points)):
        parameters.append(
            parameters[-1] + point_distance(points[index - 1], points[index])
        )
    total = parameters[-1]
    if total > 1e-12:
        return [value / total for value in parameters]
    count = len(points) - 1
    return [index / count if count > 0 else 0.0 for index in range(len(points))]


def _fallback_cubic(
    first: Point,
    last: Point,
    left_tangent: Vector2,
    right_tangent: Vector2,
) -> BezierSegment:
    distance = point_distance(first, last) / 3.0
    return _cubic_from_tangents(
        first,
        last,
        left_tangent,
        right_tangent,
        distance,
        distance,
    )


def _cubic_from_tangents(
    first: Point,
    last: Point,
    left_tangent: Vector2,
    right_tangent: Vector2,
    alpha_left: float,
    alpha_right: float,
) -> BezierSegment:
    return BezierSegment(
        start=first,
        control1=Point(
            first.x + left_tangent[0] * alpha_left,
            first.y + left_tangent[1] * alpha_left,
        ),
        control2=Point(
            last.x + right_tangent[0] * alpha_right,
            last.y + right_tangent[1] * alpha_right,
        ),
        end=last,
    )


def _segment_weight(segments: list[BezierSegment]) -> int:
    return sum(3 if isinstance(segment, BezierSegment) else 1 for segment in segments)


__all__ = [
    "chord_length_parameterize",
    "compute_max_error",
    "curve_fit",
    "eval_bezier",
    "fit_cubic_beziers",
    "fit_single_cubic",
]
