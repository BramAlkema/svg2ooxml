"""Tests for the DrawingML custom geometry generator."""

from __future__ import annotations

import pytest

from svg2ooxml.drawingml.custgeom_generator import (
    CustGeomGenerationError,
    CustGeomGenerator,
    segments_from_primitives,
)
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point


def test_generate_from_segments_returns_custom_geometry() -> None:
    generator = CustGeomGenerator()
    segments = [
        LineSegment(Point(0, 0), Point(20, 0)),
        LineSegment(Point(20, 0), Point(20, 10)),
        LineSegment(Point(20, 10), Point(0, 10)),
        LineSegment(Point(0, 10), Point(0, 0)),
    ]

    geometry = generator.generate_from_segments(segments)

    assert geometry.xml.startswith("<a:custGeom>")
    assert geometry.bounds.width == 20
    assert geometry.bounds.height == 10
    assert geometry.width_emu > 0
    assert geometry.height_emu > 0


def test_generate_from_primitives_rect_produces_geometry() -> None:
    generator = CustGeomGenerator()
    primitives = (
        {
            "type": "rect",
            "x": 0.0,
            "y": 0.0,
            "width": 15.0,
            "height": 5.0,
            "transform": (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        },
    )

    geometry = generator.generate_from_primitives(primitives)

    assert geometry.bounds.width == 15.0
    assert geometry.bounds.height == 5.0
    assert 'fill="none"' in geometry.xml
    assert 'stroke="0"' in geometry.xml


def test_segments_from_primitives_applies_transform() -> None:
    segments = segments_from_primitives(
        (
            {
                "type": "line",
                "x1": 0.0,
                "y1": 0.0,
                "x2": 2.0,
                "y2": 2.0,
                "transform": (1.0, 0.0, 0.0, 1.0, 5.0, 10.0),
            },
        )
    )

    assert len(segments) == 1
    segment = segments[0]
    assert isinstance(segment, LineSegment)
    assert segment.start.x == pytest.approx(5.0)
    assert segment.start.y == pytest.approx(10.0)
    assert segment.end.x == pytest.approx(7.0)
    assert segment.end.y == pytest.approx(12.0)


def test_segments_from_primitives_resolves_calc_line_values() -> None:
    segments = segments_from_primitives(
        (
            {
                "type": "line",
                "x1": "calc(1px + 2px)",
                "y1": "calc(2px * 2)",
                "x2": "calc(10px - 2px)",
                "y2": "calc(5px + 5px)",
            },
        )
    )

    assert len(segments) == 1
    segment = segments[0]
    assert isinstance(segment, LineSegment)
    assert segment.start == Point(3.0, 4.0)
    assert segment.end == Point(8.0, 10.0)


def test_generate_from_primitives_without_segments_raises() -> None:
    generator = CustGeomGenerator()

    with pytest.raises(CustGeomGenerationError):
        generator.generate_from_primitives(
            (
                {
                    "type": "rect",
                    "width": 0.0,
                    "height": 0.0,
                },
            )
        )


def test_segments_from_primitives_for_ellipse() -> None:
    segments = segments_from_primitives(
        (
            {
                "type": "ellipse",
                "cx": 5.0,
                "cy": 10.0,
                "rx": 3.0,
                "ry": 2.0,
                "transform": (1.0, 0.0, 0.0, 1.0, 2.0, -3.0),
            },
        )
    )

    assert len(segments) == 4
    assert all(isinstance(segment, BezierSegment) for segment in segments)
    assert segments[0].start.x == pytest.approx(5.0 + 3.0 + 2.0)
    assert segments[0].start.y == pytest.approx(10.0 - 3.0)


def test_segments_from_primitives_for_polygon_closes_loop() -> None:
    segments = segments_from_primitives(
        (
            {
                "type": "polygon",
                "points": "0,0 5,0 5,5",
                "transform": (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
            },
        )
    )

    assert len(segments) == 3
    assert segments[0].start == Point(0.0, 0.0)
    assert segments[-1].end == Point(0.0, 0.0)


def test_segments_from_primitives_parses_compact_signed_points() -> None:
    segments = segments_from_primitives(
        (
            {
                "type": "polyline",
                "points": "0,0 10-5 20,0",
                "transform": (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
            },
        )
    )

    assert len(segments) == 2
    assert segments[0].start == Point(0.0, 0.0)
    assert segments[0].end == Point(10.0, -5.0)
    assert segments[1].end == Point(20.0, 0.0)


def test_segments_from_primitives_for_path_handles_cubic_commands() -> None:
    segments = segments_from_primitives(
        (
            {
                "type": "path",
                "d": "M0 0 C 0 10 10 10 10 0 Z",
                "transform": (1.0, 0.0, 0.0, 1.0, 1.0, 2.0),
            },
        )
    )

    assert len(segments) == 2
    cubic = segments[0]
    assert isinstance(cubic, BezierSegment)
    assert cubic.start == Point(1.0, 2.0)
    assert cubic.end == Point(11.0, 2.0)


def test_segments_from_primitives_applies_skew_transform() -> None:
    segments = segments_from_primitives(
        (
            {
                "type": "line",
                "x1": 0.0,
                "y1": 0.0,
                "x2": 4.0,
                "y2": 0.0,
                # Matrix with b=0.5 applies a y shear based on x
                "transform": (1.0, 0.5, 0.0, 1.0, 0.0, 0.0),
            },
        )
    )

    assert len(segments) == 1
    segment = segments[0]
    assert isinstance(segment, LineSegment)
    assert segment.start == Point(0.0, 0.0)
    assert segment.end.x == pytest.approx(4.0)
    assert segment.end.y == pytest.approx(2.0)
