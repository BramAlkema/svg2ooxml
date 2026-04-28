"""Geometric primitives for svg2ooxml IR."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from svg2ooxml.common.numpy_compat import matmul, np, sqrt


@dataclass(frozen=True)
class Point:
    """Simple 2D point in user coordinates."""

    x: float
    y: float

    def __iter__(self):
        yield self.x
        yield self.y

    def transform(self, matrix: Sequence[Sequence[float]]) -> Point:
        """Apply a 3x3 transformation matrix."""
        vec = np.array([self.x, self.y, 1.0])
        transformed = matmul(matrix, vec)
        return Point(float(transformed[0]), float(transformed[1]))


@dataclass(frozen=True)
class Rect:
    """Axis-aligned bounding rectangle."""

    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return self.x

    @property
    def top(self) -> float:
        return self.y

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center(self) -> Point:
        return Point(self.x + self.width / 2.0, self.y + self.height / 2.0)

    def contains(self, point: Point) -> bool:
        return self.left <= point.x <= self.right and self.top <= point.y <= self.bottom

    def intersects(self, other: Rect) -> bool:
        return not (
            self.right < other.left
            or self.left > other.right
            or self.bottom < other.top
            or self.top > other.bottom
        )


@dataclass(frozen=True)
class Segment:
    """Base segment type."""


@dataclass(frozen=True)
class LineSegment(Segment):
    """Straight line segment."""

    start: Point
    end: Point

    def length(self) -> float:
        dx = self.end.x - self.start.x
        dy = self.end.y - self.start.y
        return float(sqrt(dx * dx + dy * dy))


@dataclass(frozen=True)
class BezierSegment(Segment):
    """Cubic Bezier segment."""

    start: Point
    control1: Point
    control2: Point
    end: Point

    def length_approx(self) -> float:
        """Quick approximation using control polygon length."""
        d1 = sqrt((self.control1.x - self.start.x) ** 2 + (self.control1.y - self.start.y) ** 2)
        d2 = sqrt((self.control2.x - self.control1.x) ** 2 + (self.control2.y - self.control1.y) ** 2)
        d3 = sqrt((self.end.x - self.control2.x) ** 2 + (self.end.y - self.control2.y) ** 2)
        return float(d1 + d2 + d3)

    def bbox(self) -> Rect:
        xs = [self.start.x, self.control1.x, self.control2.x, self.end.x]
        ys = [self.start.y, self.control1.y, self.control2.y, self.end.y]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return Rect(min_x, min_y, max_x - min_x, max_y - min_y)


SegmentType = LineSegment | BezierSegment


__all__ = [
    "Point",
    "Rect",
    "Segment",
    "LineSegment",
    "BezierSegment",
    "SegmentType",
]
