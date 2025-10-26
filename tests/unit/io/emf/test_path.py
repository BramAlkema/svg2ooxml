from __future__ import annotations

from svg2ooxml.io.emf.path import DashPattern, apply_dash_pattern, flatten_segments
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point


def test_flatten_segments_bezier() -> None:
    segment = BezierSegment(
        start=Point(0.0, 0.0),
        control1=Point(0.0, 10.0),
        control2=Point(10.0, 10.0),
        end=Point(10.0, 0.0),
    )
    points = flatten_segments([segment], tolerance=0.25)
    assert points[0] == (0.0, 0.0)
    assert points[-1] == (10.0, 0.0)
    assert len(points) > 4  # subdivision occurs


def test_apply_dash_pattern() -> None:
    points = [(0.0, 0.0), (10.0, 0.0)]
    pattern = DashPattern((4.0, 2.0))
    segments = apply_dash_pattern(points, pattern)
    assert len(segments) == 2
    assert segments[0][0] == (0.0, 0.0)
    assert abs(segments[0][-1][0] - 4.0) < 1e-6
