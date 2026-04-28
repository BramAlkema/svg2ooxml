"""Shared helpers for IR geometry segments."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType

PointTransform = Callable[[Point], Point]


def transform_segment(
    segment: SegmentType, transform_point: PointTransform
) -> SegmentType:
    """Apply a point transform to a line or cubic Bezier segment."""

    if isinstance(segment, LineSegment):
        return LineSegment(
            start=transform_point(segment.start),
            end=transform_point(segment.end),
        )
    if isinstance(segment, BezierSegment):
        return BezierSegment(
            start=transform_point(segment.start),
            control1=transform_point(segment.control1),
            control2=transform_point(segment.control2),
            end=transform_point(segment.end),
        )
    return segment


def transform_segments(
    segments: Iterable[SegmentType],
    transform_point: PointTransform,
) -> list[SegmentType]:
    """Apply a point transform to all supported segment types."""

    return [transform_segment(segment, transform_point) for segment in segments]


def line_segments_from_points(points: Iterable[Point]) -> list[LineSegment]:
    """Build consecutive line segments from an ordered point sequence."""

    segments: list[LineSegment] = []
    previous_point: Point | None = None
    for point in points:
        if previous_point is not None:
            segments.append(LineSegment(previous_point, point))
        previous_point = point
    return segments


__all__ = [
    "PointTransform",
    "line_segments_from_points",
    "transform_segment",
    "transform_segments",
]
