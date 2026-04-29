"""Path segment helpers interoperating with IR geometry."""

from __future__ import annotations

from collections.abc import Iterable
from math import sqrt

from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect, SegmentType

_EPSILON = 1e-6


def compute_segments_bbox(segments: Iterable[SegmentType]) -> Rect:
    """Return a curve-aware bounding box for the provided segments."""

    min_x = float("inf")
    max_x = float("-inf")
    min_y = float("inf")
    max_y = float("-inf")

    for segment in segments:
        if isinstance(segment, LineSegment):
            min_x = min(min_x, segment.start.x, segment.end.x)
            max_x = max(max_x, segment.start.x, segment.end.x)
            min_y = min(min_y, segment.start.y, segment.end.y)
            max_y = max(max_y, segment.start.y, segment.end.y)
        elif isinstance(segment, BezierSegment):
            bx_min, bx_max, by_min, by_max = _bezier_extents(segment)
            min_x = min(min_x, bx_min)
            max_x = max(max_x, bx_max)
            min_y = min(min_y, by_min)
            max_y = max(max_y, by_max)
        else:  # pragma: no cover - reserved for future segment types
            start = getattr(segment, "start", None)
            end = getattr(segment, "end", None)
            for point in (start, end):
                if point is None:
                    continue
                min_x = min(min_x, point.x)
                max_x = max(max_x, point.x)
                min_y = min(min_y, point.y)
                max_y = max(max_y, point.y)

    if min_x == float("inf") or min_y == float("inf"):
        return Rect(0.0, 0.0, 0.0, 0.0)

    width = max_x - min_x
    height = max_y - min_y
    if abs(width) <= _EPSILON:
        width = _EPSILON
    if abs(height) <= _EPSILON:
        height = _EPSILON
    return Rect(min_x, min_y, width, height)


def _bezier_extents(segment: BezierSegment) -> tuple[float, float, float, float]:
    xs = _cubic_axis_extrema(
        segment.start.x,
        segment.control1.x,
        segment.control2.x,
        segment.end.x,
    )
    ys = _cubic_axis_extrema(
        segment.start.y,
        segment.control1.y,
        segment.control2.y,
        segment.end.y,
    )
    return min(xs), max(xs), min(ys), max(ys)


def _cubic_axis_extrema(p0: float, p1: float, p2: float, p3: float) -> list[float]:
    values = [p0, p3]
    a = -p0 + 3 * p1 - 3 * p2 + p3
    b = 3 * p0 - 6 * p1 + 3 * p2
    c = -3 * p0 + 3 * p1
    roots = _solve_quadratic(3 * a, 2 * b, c)
    for t in roots:
        if 0.0 < t < 1.0:
            values.append(_evaluate_cubic(a, b, c, p0, t))
    return values


def _solve_quadratic(a: float, b: float, c: float) -> list[float]:
    if abs(a) <= _EPSILON:
        if abs(b) <= _EPSILON:
            return []
        return [(-c) / b]
    discriminant = b * b - 4.0 * a * c
    if discriminant < 0.0:
        if discriminant > -_EPSILON:
            discriminant = 0.0
        else:
            return []
    sqrt_disc = sqrt(discriminant)
    return [(-b + sqrt_disc) / (2.0 * a), (-b - sqrt_disc) / (2.0 * a)]


def _evaluate_cubic(a: float, b: float, c: float, p0: float, t: float) -> float:
    return ((a * t + b) * t + c) * t + p0


__all__ = [
    "Point",
    "LineSegment",
    "BezierSegment",
    "SegmentType",
    "compute_segments_bbox",
]
