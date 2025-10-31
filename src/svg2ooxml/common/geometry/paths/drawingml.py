"""Helpers for transforming IR path segments into DrawingML-ready data."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import List, Sequence

from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect, SegmentType

_EPSILON = 1e-6


@dataclass(frozen=True)
class PathCommand:
    """High-level DrawingML command."""

    name: str
    points: tuple[Point, ...] = ()


def compute_path_bounds(segments: Sequence[SegmentType]) -> Rect:
    """Return a tight bounding box for the provided path segments."""

    if not segments:
        return Rect(0.0, 0.0, 0.0, 0.0)

    min_x = float("inf")
    max_x = float("-inf")
    min_y = float("inf")
    max_y = float("-inf")

    for segment in segments:
        if isinstance(segment, LineSegment):
            candidates = (segment.start, segment.end)
            for point in candidates:
                min_x = min(min_x, point.x)
                max_x = max(max_x, point.x)
                min_y = min(min_y, point.y)
                max_y = max(max_y, point.y)
        elif isinstance(segment, BezierSegment):
            bx_min, bx_max, by_min, by_max = _bezier_extents(segment)
            min_x = min(min_x, bx_min)
            max_x = max(max_x, bx_max)
            min_y = min(min_y, by_min)
            max_y = max(max_y, by_max)
        else:  # pragma: no cover - future segment types
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


def build_path_commands(segments: Sequence[SegmentType], *, closed: bool) -> list[PathCommand]:
    """Translate segments into DrawingML path commands."""

    if not segments:
        return []

    commands: list[PathCommand] = []
    subpaths = _split_subpaths(segments)

    for index, subpath in enumerate(subpaths):
        first_segment = subpath[0]
        start_point = getattr(first_segment, "start", None)
        if start_point is None:
            continue
        commands.append(PathCommand("moveTo", (start_point,)))
        current = start_point

        for segment in subpath:
            if isinstance(segment, LineSegment):
                commands.append(PathCommand("lnTo", (segment.end,)))
                current = segment.end
            elif isinstance(segment, BezierSegment):
                commands.append(
                    PathCommand(
                        "cubicBezTo",
                        (segment.control1, segment.control2, segment.end),
                    )
                )
                current = segment.end
            else:  # pragma: no cover - reserved for future segment types
                end_point = getattr(segment, "end", None)
                if end_point is not None:
                    commands.append(PathCommand("lnTo", (end_point,)))
                    current = end_point

        last_segment = subpath[-1]
        last_point = getattr(last_segment, "end", None)
        should_close = False
        if last_point is not None and _points_close(start_point, last_point):
            should_close = True
        elif closed and index == len(subpaths) - 1:
            should_close = True

        if should_close:
            commands.append(PathCommand("close"))
            current = start_point

    return commands


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _split_subpaths(segments: Sequence[SegmentType]) -> list[list[SegmentType]]:
    subpaths: list[list[SegmentType]] = []
    current: list[SegmentType] = []
    previous_endpoint: Point | None = None

    for segment in segments:
        start = getattr(segment, "start", None)
        if start is None:
            continue
        if previous_endpoint is None or not _points_close(previous_endpoint, start):
            if current:
                subpaths.append(current)
                current = []
        current.append(segment)
        previous_endpoint = getattr(segment, "end", start)

    if current:
        subpaths.append(current)
    return subpaths


def _points_close(a: Point, b: Point, *, tolerance: float = 1e-4) -> bool:
    return abs(a.x - b.x) <= tolerance and abs(a.y - b.y) <= tolerance


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


def _cubic_axis_extrema(p0: float, p1: float, p2: float, p3: float) -> List[float]:
    """Return axis values (including extrema) for a cubic Bezier."""

    values = [p0, p3]
    a = -p0 + 3 * p1 - 3 * p2 + p3
    b = 3 * p0 - 6 * p1 + 3 * p2
    c = -3 * p0 + 3 * p1
    # derivative coefficients for cubic bezier
    A = 3 * a
    B = 2 * b
    C = c

    roots = _solve_quadratic(A, B, C)
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


__all__ = ["PathCommand", "build_path_commands", "compute_path_bounds"]
