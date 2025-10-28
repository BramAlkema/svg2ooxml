"""Geometry helper utilities shared across converter modules."""

from __future__ import annotations

from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.common.geometry import Matrix2D


def is_axis_aligned(matrix: Matrix2D, tolerance: float = 1e-6) -> bool:
    """Return True when transform does not skew axes."""

    return abs(matrix.b) <= tolerance and abs(matrix.c) <= tolerance


def scaled_corner_radius(radius: float, matrix: Matrix2D, tolerance: float = 1e-6) -> float:
    """Scale a corner radius by the axis-aligned transform components."""

    if radius <= tolerance:
        return 0.0
    if not is_axis_aligned(matrix, tolerance):
        return radius
    scale_x = abs(matrix.a)
    scale_y = abs(matrix.d)
    scale = min(
        scale_x if scale_x > tolerance else 1.0,
        scale_y if scale_y > tolerance else 1.0,
    )
    return radius * scale


def transform_axis_aligned_rect(
    matrix: Matrix2D,
    x: float,
    y: float,
    width: float,
    height: float,
    tolerance: float = 1e-6,
) -> Rect | None:
    """Transform an axis-aligned rectangle and return its bounds."""

    corners = [
        matrix.transform_point(Point(x, y)),
        matrix.transform_point(Point(x + width, y)),
        matrix.transform_point(Point(x, y + height)),
        matrix.transform_point(Point(x + width, y + height)),
    ]
    xs = [pt.x for pt in corners]
    ys = [pt.y for pt in corners]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    transformed_width = max_x - min_x
    transformed_height = max_y - min_y
    if transformed_width <= tolerance or transformed_height <= tolerance:
        return None
    return Rect(x=min_x, y=min_y, width=transformed_width, height=transformed_height)


__all__ = ["is_axis_aligned", "scaled_corner_radius", "transform_axis_aligned_rect"]
