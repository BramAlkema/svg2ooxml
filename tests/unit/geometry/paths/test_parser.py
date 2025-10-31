"""Tests for geometry path parser."""

import pytest

from svg2ooxml.common.geometry.paths import (
    BezierSegment,
    LineSegment,
    Point,
    compute_segments_bbox,
    parse_path_data,
)


def test_parse_line_commands() -> None:
    segments = parse_path_data("M 0 0 L 10 0 l 0 5 z")

    assert len(segments) == 3
    assert isinstance(segments[0], LineSegment)
    assert segments[0].end == Point(10, 0)
    assert isinstance(segments[-1], LineSegment)
    assert segments[-1].end == Point(0, 0)


def test_parse_cubic_curve() -> None:
    segments = parse_path_data("M0,0 C10,0 10,10 20,10")

    assert len(segments) == 1
    seg = segments[0]
    assert isinstance(seg, BezierSegment)
    assert seg.control1 == Point(10, 0)
    assert seg.control2 == Point(10, 10)
    assert seg.end == Point(20, 10)


def test_parse_smooth_cubic_curve() -> None:
    segments = parse_path_data("M0 0 C10 0 10 10 20 10 S30 20 40 10")

    assert len(segments) == 2
    first, second = segments
    assert isinstance(first, BezierSegment)
    assert isinstance(second, BezierSegment)
    assert second.control1 == Point(30, 10)  # reflected control from previous segment
    assert second.end == Point(40, 10)


def test_parse_quadratic_and_smooth_quadratic() -> None:
    segments = parse_path_data("M0 0 Q10 10 20 0 T40 0")

    assert len(segments) == 2
    first, second = segments
    assert isinstance(first, BezierSegment)
    assert isinstance(second, BezierSegment)
    assert first.end == Point(20, 0)
    assert second.end == Point(40, 0)
    assert second.control1.x == pytest.approx(26.6666667, rel=1e-6)
    assert second.control1.y == pytest.approx(-6.6666667, rel=1e-6)


def test_compute_segments_bbox() -> None:
    segments = [
        LineSegment(Point(0, 0), Point(4, 0)),
        LineSegment(Point(4, 0), Point(4, 3)),
    ]

    bbox = compute_segments_bbox(segments)

    assert bbox.width == 4
    assert bbox.height == 3


def test_parse_arc_command() -> None:
    segments = parse_path_data("M 0 0 A 10 10 0 0 1 10 10")

    assert segments
    assert isinstance(segments[0], BezierSegment)
    end_point = segments[-1].end
    assert end_point.x == pytest.approx(10.0)
    assert end_point.y == pytest.approx(10.0)
