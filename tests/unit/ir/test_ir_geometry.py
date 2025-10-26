"""Tests for IR geometry primitives."""

from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect
from svg2ooxml.ir.numpy_compat import np


def test_point_transform_identity() -> None:
    point = Point(10, 5)
    matrix = np.identity(3) if hasattr(np, "identity") else ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

    transformed = point.transform(matrix)

    assert transformed.x == 10
    assert transformed.y == 5


def test_line_segment_length() -> None:
    segment = LineSegment(Point(0, 0), Point(3, 4))

    assert segment.length() == 5


def test_bezier_bbox() -> None:
    bezier = BezierSegment(
        start=Point(0, 0),
        control1=Point(1, 2),
        control2=Point(2, 3),
        end=Point(4, 5),
    )

    bbox = bezier.bbox()

    assert isinstance(bbox, Rect)
    assert bbox.width == 4
    assert bbox.height == 5
