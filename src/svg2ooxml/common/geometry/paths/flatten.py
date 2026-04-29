"""Curve flattening helpers for SVG path geometry."""

from __future__ import annotations

import math

from svg2ooxml.common.geometry.paths.quadratic import (
    quadratic_tuple_to_cubic_controls,
)

PointTuple = tuple[float, float]


def flatten_cubic_points(
    p0: PointTuple,
    p1: PointTuple,
    p2: PointTuple,
    p3: PointTuple,
    tolerance: float,
) -> list[PointTuple]:
    """Flatten a cubic Bezier into points using recursive subdivision."""

    def recursive(
        a: PointTuple,
        b: PointTuple,
        c: PointTuple,
        d: PointTuple,
    ) -> list[PointTuple]:
        max_dist = max(
            distance_point_to_line(b, a, d),
            distance_point_to_line(c, a, d),
        )
        if max_dist <= tolerance:
            return [a, d]
        ab = midpoint(a, b)
        bc = midpoint(b, c)
        cd = midpoint(c, d)
        abc = midpoint(ab, bc)
        bcd = midpoint(bc, cd)
        abcd = midpoint(abc, bcd)
        left = recursive(a, ab, abc, abcd)
        right = recursive(abcd, bcd, cd, d)
        return left[:-1] + right

    return recursive(p0, p1, p2, p3)


def flatten_quadratic_points(
    p0: PointTuple,
    p1: PointTuple,
    p2: PointTuple,
    tolerance: float,
) -> list[PointTuple]:
    """Flatten a quadratic Bezier into points via cubic conversion."""

    c1, c2 = quadratic_tuple_to_cubic_controls(p0, p1, p2)
    return flatten_cubic_points(p0, c1, c2, p2, tolerance)


def distance_point_to_line(
    point: PointTuple,
    start: PointTuple,
    end: PointTuple,
) -> float:
    """Return perpendicular distance from ``point`` to the line ``start``-``end``."""

    x0, y0 = point
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x0 - x1, y0 - y1)
    return abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / math.hypot(dx, dy)


def midpoint(p1: PointTuple, p2: PointTuple) -> PointTuple:
    """Return the midpoint between two 2D points."""

    return ((p1[0] + p2[0]) * 0.5, (p1[1] + p2[1]) * 0.5)


__all__ = [
    "PointTuple",
    "distance_point_to_line",
    "flatten_cubic_points",
    "flatten_quadratic_points",
    "midpoint",
]
