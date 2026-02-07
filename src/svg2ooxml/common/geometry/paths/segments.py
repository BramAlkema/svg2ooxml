"""Path segment helpers interoperating with IR geometry."""

from __future__ import annotations

from collections.abc import Iterable

from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect, SegmentType


def compute_segments_bbox(segments: Iterable[SegmentType]) -> Rect:
    """Return a conservative bounding box covering all segment points."""
    xs: list[float] = []
    ys: list[float] = []

    for segment in segments:
        if isinstance(segment, LineSegment):
            xs.extend([segment.start.x, segment.end.x])
            ys.extend([segment.start.y, segment.end.y])
        elif isinstance(segment, BezierSegment):
            xs.extend(
                [
                    segment.start.x,
                    segment.control1.x,
                    segment.control2.x,
                    segment.end.x,
                ]
            )
            ys.extend(
                [
                    segment.start.y,
                    segment.control1.y,
                    segment.control2.y,
                    segment.end.y,
                ]
            )

    if not xs or not ys:
        return Rect(0.0, 0.0, 0.0, 0.0)

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    return Rect(min_x, min_y, max_x - min_x, max_y - min_y)


__all__ = [
    "Point",
    "LineSegment",
    "BezierSegment",
    "SegmentType",
    "compute_segments_bbox",
]
