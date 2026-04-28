"""Quadratic Bezier conversion helpers."""

from __future__ import annotations

from svg2ooxml.ir.geometry import BezierSegment, Point

PointTuple = tuple[float, float]
_QUADRATIC_TO_CUBIC_WEIGHT = 2.0 / 3.0


def quadratic_to_cubic_controls(
    start: Point,
    control: Point,
    end: Point,
) -> tuple[Point, Point]:
    """Return cubic control points equivalent to a quadratic Bezier."""

    c1, c2 = quadratic_tuple_to_cubic_controls(
        (start.x, start.y),
        (control.x, control.y),
        (end.x, end.y),
    )
    return Point(*c1), Point(*c2)


def quadratic_to_cubic(
    start: Point,
    control: Point,
    end: Point,
) -> BezierSegment:
    """Convert a quadratic Bezier to an equivalent cubic Bezier segment."""

    control1, control2 = quadratic_to_cubic_controls(start, control, end)
    return BezierSegment(start, control1, control2, end)


def quadratic_tuple_to_cubic_controls(
    start: PointTuple,
    control: PointTuple,
    end: PointTuple,
) -> tuple[PointTuple, PointTuple]:
    """Return cubic control points for tuple-based quadratic geometry."""

    return (
        (
            start[0] + _QUADRATIC_TO_CUBIC_WEIGHT * (control[0] - start[0]),
            start[1] + _QUADRATIC_TO_CUBIC_WEIGHT * (control[1] - start[1]),
        ),
        (
            end[0] + _QUADRATIC_TO_CUBIC_WEIGHT * (control[0] - end[0]),
            end[1] + _QUADRATIC_TO_CUBIC_WEIGHT * (control[1] - end[1]),
        ),
    )


__all__ = [
    "quadratic_to_cubic",
    "quadratic_to_cubic_controls",
    "quadratic_tuple_to_cubic_controls",
]
