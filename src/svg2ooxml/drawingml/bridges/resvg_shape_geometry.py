"""Shared geometry helpers for ``ResvgShapeAdapter``."""

from __future__ import annotations

from svg2ooxml.core.ir.shape_converters_utils import _ellipse_segments
from svg2ooxml.ir.geometry import Point, SegmentType


class ResvgShapeGeometryMixin:
    """Basic shape geometry utilities."""

    @staticmethod
    def _normalized_corner_radii(
        rx: float,
        ry: float,
        width: float,
        height: float,
    ) -> tuple[float, float]:
        """Apply SVG rounded-rectangle radius fallback and clamping."""
        if rx > 0 and ry <= 0:
            ry = rx
        elif ry > 0 and rx <= 0:
            rx = ry
        return (min(rx, width / 2.0), min(ry, height / 2.0))

    def _ellipse_segments(
        self, cx: float, cy: float, rx: float, ry: float
    ) -> list[SegmentType]:
        """Generate IR segments for an ellipse using cubic Bezier approximation."""
        return _ellipse_segments(cx, cy, rx, ry)

    def _points_from_flat(self, values: tuple[float, ...]) -> list[Point]:
        """Convert a flat tuple of floats into a list of Points."""
        if len(values) < 2:
            return []
        points: list[Point] = []
        for i in range(0, len(values) - 1, 2):
            points.append(Point(values[i], values[i + 1]))
        return points

    def _points_close(self, a: Point, b: Point, tol: float = 1e-9) -> bool:
        """Return True if two points are effectively identical."""
        return abs(a.x - b.x) < tol and abs(a.y - b.y) < tol


__all__ = ["ResvgShapeGeometryMixin"]
