"""Tests for pure motion path helpers."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from svg2ooxml.common.geometry.paths.segments import BezierSegment, LineSegment
from svg2ooxml.drawingml.animation.handlers import motion_path
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    CalcMode,
)
from svg2ooxml.ir.geometry import Point


def make_motion_animation(**overrides) -> AnimationDefinition:
    """Build a real AnimationDefinition for motion path helpers."""

    defaults = dict(
        element_id="shape1",
        animation_type=AnimationType.ANIMATE_MOTION,
        target_attribute="d",
        values=["M0,0 L100,100"],
        timing=AnimationTiming(begin=0.0, duration=1.0),
    )
    defaults.update(overrides)
    return AnimationDefinition(**defaults)


def test_build_motion_path_string_uses_start_relative_slide_fractions() -> None:
    anim = make_motion_animation(motion_viewport_px=(200.0, 400.0))

    path = motion_path.build_motion_path_string(
        [(50.0, 60.0), (150.0, 260.0)],
        anim,
    )

    assert path == "M 0 0 L 0.5 0.5 E"


def test_linear_calc_mode_without_key_times_retimes_each_value_equally() -> None:
    anim = make_motion_animation(
        values=["M0,200 L0,167 L0,111 L0,0"],
        calc_mode=CalcMode.LINEAR,
    )

    points = motion_path.retime_motion_points(
        [(0.0, 200.0), (0.0, 167.0), (0.0, 111.0), (0.0, 0.0)],
        anim,
    )

    assert len(points) > 4
    assert points.index((0.0, 167.0)) == 32
    assert points.index((0.0, 111.0)) == 64


def test_paced_calc_mode_without_key_times_uses_distance_weighting() -> None:
    anim = make_motion_animation(
        values=["M0,200 L0,167 L0,111 L0,0"],
        calc_mode=CalcMode.PACED,
    )

    points = motion_path.retime_motion_points(
        [(0.0, 200.0), (0.0, 167.0), (0.0, 111.0), (0.0, 0.0)],
        anim,
    )

    assert len(points) > 4
    assert points.index((0.0, 167.0)) == 16
    assert points.index((0.0, 111.0)) == 43


def test_key_points_retime_path_progress() -> None:
    anim = make_motion_animation(
        values=["M0,0 L100,0"],
        key_times=[0.0, 0.5, 1.0],
        key_points=[0.0, 1.0, 0.5],
        calc_mode=CalcMode.LINEAR,
    )

    points = motion_path.retime_motion_points(
        [(0.0, 0.0), (100.0, 0.0)],
        anim,
    )

    assert points[0] == (0.0, 0.0)
    assert points[48] == (100.0, 0.0)
    assert points[-1] == (50.0, 0.0)


def test_discrete_retime_holds_previous_point_until_next_slot() -> None:
    expanded = motion_path.expand_discrete_points(
        points=[(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)],
        key_times=[0.0, 0.25, 1.0],
        segment_budget=4,
    )

    assert expanded == [
        (0.0, 0.0),
        (10.0, 0.0),
        (10.0, 0.0),
        (10.0, 0.0),
        (20.0, 0.0),
    ]


def test_sample_points_at_progress_uses_distance_along_polyline() -> None:
    points = motion_path.sample_points_at_progress(
        [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)],
        [0.0, 0.5, 1.0],
    )

    assert points == [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]


def test_sample_polyline_at_distance_interpolates_inside_segment() -> None:
    point = motion_path.sample_polyline_at_distance(
        points=[(0.0, 0.0), (10.0, 0.0)],
        cumulative_lengths=[0.0, 10.0],
        target_distance=2.5,
    )

    assert point == (2.5, 0.0)


def test_projects_motion_path_into_absolute_shape_positions() -> None:
    anim = make_motion_animation(
        motion_space_matrix=(1.0, 0.0, 0.0, 1.0, 50.0, 90.0),
        element_motion_offset_px=(0.0, -19.2),
    )

    projected = motion_path.project_motion_points(
        [(0.0, 0.0), (50.0, 180.0)],
        anim,
    )

    assert projected == [(50.0, 70.8), (100.0, 250.8)]


def test_projects_motion_path_with_shape_anchor_offset() -> None:
    anim = make_motion_animation(
        element_motion_offset_px=(-30.0, -60.0),
    )

    projected = motion_path.project_motion_points(
        [(90.0, 258.0), (390.0, 180.0)],
        anim,
    )

    assert projected == [(60.0, 198.0), (360.0, 120.0)]


def test_resolves_exact_initial_tangent_for_cubic_motion_path() -> None:
    anim = make_motion_animation(
        motion_space_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
    )

    angle = motion_path.resolve_exact_initial_tangent_angle(
        "M25,225 C25,175 125,150 175,200",
        anim,
        "auto",
    )

    assert angle == pytest.approx(-90.0)


def test_resolves_exact_initial_tangent_relative_to_element_heading() -> None:
    anim = make_motion_animation(
        motion_space_matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        element_heading_deg=-90.0,
    )

    angle = motion_path.resolve_exact_initial_tangent_angle(
        "M25,225 C25,175 125,150 175,200",
        anim,
        "auto",
    )

    assert angle == pytest.approx(0.0)


def test_sample_path_tangent_angles_unwraps_auto_reverse_turns() -> None:
    angles = motion_path.sample_path_tangent_angles(
        [(0.0, 0.0), (-1.0, 0.1), (-2.0, 0.0)],
        "auto-reverse",
    )

    assert angles[0] == pytest.approx(354.2894068625)
    assert angles[-1] == pytest.approx(365.7105931375)
    assert motion_path.has_dynamic_rotation(angles)


def test_parse_motion_path_returns_empty_for_empty_path() -> None:
    assert motion_path.parse_motion_path("") == []


def test_parse_motion_path_parses_simple_move_line_path(monkeypatch) -> None:
    mock_parse = Mock()
    start = Point(x=0, y=0)
    end = Point(x=100, y=100)
    segment = LineSegment(start=start, end=end)
    mock_parse.return_value = [segment]
    monkeypatch.setattr(
        "svg2ooxml.common.geometry.paths.parse_path_data",
        mock_parse,
    )

    result = motion_path.parse_motion_path("M0,0 L100,100")

    assert result == [(0.0, 0.0), (100.0, 100.0)]


def test_parse_motion_path_samples_bezier_curves(monkeypatch) -> None:
    mock_parse = Mock()
    start = Point(x=0, y=0)
    control1 = Point(x=50, y=0)
    control2 = Point(x=50, y=100)
    end = Point(x=100, y=100)
    segment = BezierSegment(
        start=start,
        control1=control1,
        control2=control2,
        end=end,
    )
    mock_parse.return_value = [segment]
    monkeypatch.setattr(
        "svg2ooxml.common.geometry.paths.parse_path_data",
        mock_parse,
    )

    result = motion_path.parse_motion_path("M0,0 C50,0 50,100 100,100")

    assert len(result) > 2
    assert result[0] == (0.0, 0.0)
    assert abs(result[-1][0] - 100.0) < 1.0
    assert abs(result[-1][1] - 100.0) < 1.0


def test_parse_motion_path_deduplicates_consecutive_points(monkeypatch) -> None:
    mock_parse = Mock()
    start = Point(x=0, y=0)
    mid = Point(x=0, y=0)
    end = Point(x=100, y=100)
    segments = [
        LineSegment(start=start, end=mid),
        LineSegment(start=mid, end=end),
    ]
    mock_parse.return_value = segments
    monkeypatch.setattr(
        "svg2ooxml.common.geometry.paths.parse_path_data",
        mock_parse,
    )

    result = motion_path.parse_motion_path("M0,0 L0,0 L100,100")

    assert result == [(0.0, 0.0), (100.0, 100.0)]


def test_parse_motion_path_handles_path_parse_error(monkeypatch) -> None:
    from svg2ooxml.common.geometry.paths import PathParseError

    mock_parse = Mock(side_effect=PathParseError("Invalid path"))
    monkeypatch.setattr(
        "svg2ooxml.common.geometry.paths.parse_path_data",
        mock_parse,
    )

    assert motion_path.parse_motion_path("INVALID") == []


def test_sample_bezier_samples_cubic_bezier_curve() -> None:
    segment = BezierSegment(
        start=Point(x=0, y=0),
        control1=Point(x=50, y=0),
        control2=Point(x=50, y=100),
        end=Point(x=100, y=100),
    )

    result = motion_path.sample_bezier(segment, steps=10)

    assert len(result) == 10
    assert all(isinstance(point, Point) for point in result)
    assert abs(result[-1].x - 100.0) < 1.0
    assert abs(result[-1].y - 100.0) < 1.0


def test_bezier_point_returns_start_at_t_zero() -> None:
    segment = BezierSegment(
        start=Point(x=0, y=0),
        control1=Point(x=50, y=0),
        control2=Point(x=50, y=100),
        end=Point(x=100, y=100),
    )

    result = motion_path.bezier_point(segment, 0.0)

    assert abs(result.x) < 0.001
    assert abs(result.y) < 0.001


def test_bezier_point_returns_end_at_t_one() -> None:
    segment = BezierSegment(
        start=Point(x=0, y=0),
        control1=Point(x=50, y=0),
        control2=Point(x=50, y=100),
        end=Point(x=100, y=100),
    )

    result = motion_path.bezier_point(segment, 1.0)

    assert abs(result.x - 100.0) < 0.001
    assert abs(result.y - 100.0) < 0.001


def test_dedupe_points_removes_exact_consecutive_duplicates() -> None:
    points = [Point(x=0, y=0), Point(x=0, y=0), Point(x=100, y=100)]

    result = motion_path.dedupe_points(points)

    assert result == [(0.0, 0.0), (100.0, 100.0)]


def test_dedupe_points_keeps_non_consecutive_duplicates() -> None:
    points = [Point(x=0, y=0), Point(x=50, y=50), Point(x=0, y=0)]

    result = motion_path.dedupe_points(points)

    assert result == [(0.0, 0.0), (50.0, 50.0), (0.0, 0.0)]


def test_dedupe_points_handles_empty_list() -> None:
    assert motion_path.dedupe_points([]) == []


def test_simple_path_parse_parses_move_and_line() -> None:
    result = motion_path.simple_path_parse("M 0 0 L 100 100")

    assert result == [(0.0, 0.0), (100.0, 100.0)]


def test_simple_path_parse_handles_comma_separated_values() -> None:
    result = motion_path.simple_path_parse("M 0,0 L 100,100")

    assert result == [(0.0, 0.0), (100.0, 100.0)]


def test_simple_path_parse_handles_multiple_lines() -> None:
    result = motion_path.simple_path_parse("M 0 0 L 50 50 L 100 100")

    assert result == [(0.0, 0.0), (50.0, 50.0), (100.0, 100.0)]


def test_simple_path_parse_handles_empty_string() -> None:
    assert motion_path.simple_path_parse("") == []
