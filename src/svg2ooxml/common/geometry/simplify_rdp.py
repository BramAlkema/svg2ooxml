"""Ramer-Douglas-Peucker simplification for line runs."""

from __future__ import annotations

from svg2ooxml.common.geometry.points import point_to_line_distance
from svg2ooxml.common.geometry.segments import line_segments_from_points
from svg2ooxml.common.geometry.simplify_runs import map_line_runs, run_to_points
from svg2ooxml.ir.geometry import LineSegment, Point, SegmentType


def rdp_simplify(
    segments: list[SegmentType],
    tolerance: float,
    epsilon: float,
) -> list[SegmentType]:
    """Apply RDP to maximal connected runs of line segments."""

    if len(segments) < 3:
        return segments

    def transform(run: list[LineSegment]) -> list[SegmentType]:
        if len(run) < 3:
            return list(run)
        return list(
            line_segments_from_points(rdp_points(run_to_points(run), tolerance))
        )

    return map_line_runs(segments, epsilon, transform)


def rdp_points(points: list[Point], tolerance: float) -> list[Point]:
    """Ramer-Douglas-Peucker simplification on a point sequence."""

    if len(points) <= 2:
        return points

    max_distance = 0.0
    max_index = 0
    for index in range(1, len(points) - 1):
        distance = point_to_line_distance(points[index], points[0], points[-1])
        if distance > max_distance:
            max_distance = distance
            max_index = index

    if max_distance > tolerance:
        left = rdp_points(points[: max_index + 1], tolerance)
        right = rdp_points(points[max_index:], tolerance)
        return left[:-1] + right
    return [points[0], points[-1]]


__all__ = ["rdp_points", "rdp_simplify"]
