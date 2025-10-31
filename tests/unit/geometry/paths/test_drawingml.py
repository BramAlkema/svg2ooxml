"""Tests for DrawingML path helpers."""

from __future__ import annotations

from svg2ooxml.common.geometry.paths.drawingml import build_path_commands, compute_path_bounds
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point


def test_compute_path_bounds_accounts_for_bezier_extrema() -> None:
    segment = BezierSegment(
        start=Point(0.0, 0.0),
        control1=Point(0.0, 100.0),
        control2=Point(100.0, 100.0),
        end=Point(100.0, 0.0),
    )

    bounds = compute_path_bounds([segment])

    assert bounds.x == 0.0
    assert bounds.y == 0.0
    assert bounds.width == 100.0
    # Extreme point occurs at t=0.5 -> y=75.0
    assert bounds.height == 75.0


def test_build_path_commands_splits_subpaths_and_closes() -> None:
    segments = [
        LineSegment(Point(0.0, 0.0), Point(10.0, 0.0)),
        LineSegment(Point(10.0, 0.0), Point(10.0, 10.0)),
        LineSegment(Point(10.0, 10.0), Point(0.0, 10.0)),
        LineSegment(Point(0.0, 10.0), Point(0.0, 0.0)),
        # start a new subpath
        LineSegment(Point(20.0, 20.0), Point(30.0, 20.0)),
    ]

    commands = build_path_commands(segments, closed=True)
    names = [cmd.name for cmd in commands]

    assert names.count("moveTo") == 2
    assert names.count("lnTo") == 5
    assert names.count("close") == 2
    assert commands[0].points[0] == Point(0.0, 0.0)
    assert commands[-1].name == "close"
