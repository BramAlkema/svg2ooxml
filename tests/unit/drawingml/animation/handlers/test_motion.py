"""Tests for MotionAnimationHandler."""

from unittest.mock import Mock, MagicMock, call
import pytest

from svg2ooxml.drawingml.animation.handlers.motion import MotionAnimationHandler
from svg2ooxml.ir.geometry import Point
from svg2ooxml.common.geometry.paths.segments import LineSegment, BezierSegment


@pytest.fixture
def xml_builder():
    """Mock XML builder."""
    builder = Mock()
    builder.build_behavior_core.return_value = (
        '                                        <a:cBhvr>\n'
        '                                            <a:cTn id="2" dur="1000" fill="hold"/>\n'
        '                                            <a:tgtEl>\n'
        '                                                <a:spTgt spid="shape1"/>\n'
        '                                            </a:tgtEl>\n'
        '                                        </a:cBhvr>\n'
    )
    builder.build_par_container.return_value = (
        '<p:par>\n'
        '    <p:cTn id="1" dur="1000" fill="hold">\n'
        '        <p:stCondLst>\n'
        '            <p:cond delay="0"/>\n'
        '        </p:stCondLst>\n'
        '        <p:childTnLst>\n'
        '            <CHILD_XML/>\n'
        '        </p:childTnLst>\n'
        '    </p:cTn>\n'
        '</p:par>'
    )
    return builder


@pytest.fixture
def value_processor():
    """Mock value processor."""
    return Mock()


@pytest.fixture
def tav_builder():
    """Mock TAV builder."""
    return Mock()


@pytest.fixture
def unit_converter():
    """Mock unit converter."""
    converter = Mock()
    converter.to_emu.side_effect = lambda val, axis: val * 914400 / 96  # 96 DPI
    return converter


@pytest.fixture
def handler(xml_builder, value_processor, tav_builder, unit_converter):
    """Create MotionAnimationHandler instance."""
    return MotionAnimationHandler(
        xml_builder=xml_builder,
        value_processor=value_processor,
        tav_builder=tav_builder,
        unit_converter=unit_converter,
    )


class TestCanHandle:
    """Tests for can_handle method."""

    def test_handles_animation_with_is_motion_true(self, handler):
        """Should handle animation with is_motion=True."""
        animation = Mock(is_motion=True)
        assert handler.can_handle(animation) is True

    def test_handles_animation_with_is_motion_false(self, handler):
        """Should not handle animation with is_motion=False."""
        animation = Mock(is_motion=False, spec=["is_motion"])
        assert handler.can_handle(animation) is False

    def test_handles_animation_with_motion_animation_type(self, handler):
        """Should handle animation with MOTION animation_type."""
        animation = Mock(spec=["animation_type"])
        animation.animation_type = "ANIMATE_MOTION"
        assert handler.can_handle(animation) is True

    def test_handles_animation_with_animate_motion_type(self, handler):
        """Should handle animation with animateMotion type."""
        animation = Mock(spec=["animation_type"])
        animation.animation_type = "animateMotion"
        assert handler.can_handle(animation) is True

    def test_rejects_non_motion_animation(self, handler):
        """Should reject non-motion animations."""
        animation = Mock(spec=["animation_type"])
        animation.animation_type = "animate"
        assert handler.can_handle(animation) is False

    def test_rejects_animation_without_motion_indicators(self, handler):
        """Should reject animations without is_motion or animation_type."""
        animation = Mock(spec=["attribute_name"])
        animation.attribute_name = "x"
        assert handler.can_handle(animation) is False


class TestBuild:
    """Tests for build method."""

    def test_returns_empty_string_when_no_values(self, handler):
        """Should return empty string when animation has no values."""
        animation = Mock(
            values=[],
            duration_ms=1000,
            begin_ms=0,
            element_id="shape1",
        )
        result = handler.build(animation, par_id=1, behavior_id=2)
        assert result == ""

    def test_returns_empty_string_when_less_than_two_points(self, handler):
        """Should return empty string when path has less than 2 points."""
        animation = Mock(
            values=["M0,0"],  # Only one point
            duration_ms=1000,
            begin_ms=0,
            element_id="shape1",
        )
        result = handler.build(animation, par_id=1, behavior_id=2)
        assert result == ""

    def test_builds_simple_linear_motion(self, handler, xml_builder, unit_converter):
        """Should build motion animation for simple linear path."""
        animation = Mock(
            values=["M0,0 L100,100"],
            duration_ms=1000,
            begin_ms=0,
            element_id="shape1",
        )

        result = handler.build(animation, par_id=1, behavior_id=2)

        # Should convert points to EMU
        assert unit_converter.to_emu.call_count >= 4  # At least 2 points with x,y

        # Should build behavior core
        xml_builder.build_behavior_core.assert_called_once_with(
            behavior_id=2,
            duration_ms=1000,
            target_shape="shape1",
        )

        # Should build par container
        xml_builder.build_par_container.assert_called_once()
        call_args = xml_builder.build_par_container.call_args
        assert call_args[1]["par_id"] == 1
        assert call_args[1]["duration_ms"] == 1000
        assert call_args[1]["delay_ms"] == 0

        # Should contain animMotion and ptLst
        child_xml = call_args[1].get("child_content") or call_args[1]["child_xml"]
        assert "<a:animMotion>" in child_xml
        assert "<a:ptLst>" in child_xml
        assert "</a:ptLst>" in child_xml
        assert "<a:pt x=" in child_xml
        assert "</a:animMotion>" in child_xml

    def test_includes_multiple_points_in_path(self, handler, xml_builder):
        """Should include all points from path in ptLst."""
        animation = Mock(
            values=["M0,0 L50,50 L100,100"],
            duration_ms=1000,
            begin_ms=0,
            element_id="shape1",
        )

        handler.build(animation, par_id=1, behavior_id=2)

        child_xml = xml_builder.build_par_container.call_args[1].get("child_content") or call_args[1]["child_xml"]
        # Should have 3 points
        assert child_xml.count("<a:pt x=") == 3

    def test_converts_points_to_emu(self, handler, unit_converter, xml_builder):
        """Should convert pixel coordinates to EMU."""
        animation = Mock(
            values=["M10,20 L30,40"],
            duration_ms=1000,
            begin_ms=0,
            element_id="shape1",
        )

        handler.build(animation, par_id=1, behavior_id=2)

        # Verify to_emu calls for both points
        calls = unit_converter.to_emu.call_args_list
        # First point (10, 20)
        assert call(10.0, axis="x") in calls
        assert call(20.0, axis="y") in calls
        # Second point (30, 40)
        assert call(30.0, axis="x") in calls
        assert call(40.0, axis="y") in calls

    def test_handles_begin_delay(self, handler, xml_builder):
        """Should pass begin_ms as delay to par container."""
        animation = Mock(
            values=["M0,0 L100,100"],
            duration_ms=1000,
            begin_ms=500,
            element_id="shape1",
        )

        handler.build(animation, par_id=1, behavior_id=2)

        call_args = xml_builder.build_par_container.call_args
        assert call_args[1]["delay_ms"] == 500

    def test_handles_missing_element_id(self, handler, xml_builder):
        """Should handle missing element_id gracefully."""
        animation = Mock(
            values=["M0,0 L100,100"],
            duration_ms=1000,
            begin_ms=0,
            spec=["values", "duration_ms", "begin_ms"],  # No element_id
        )

        result = handler.build(animation, par_id=1, behavior_id=2)

        # Should still build (with empty target)
        xml_builder.build_behavior_core.assert_called_once()
        assert xml_builder.build_behavior_core.call_args[1]["target_shape"] == ""


class TestParseMotionPath:
    """Tests for _parse_motion_path method."""

    def test_returns_empty_for_empty_path(self, handler):
        """Should return empty list for empty path."""
        result = handler._parse_motion_path("")
        assert result == []

    def test_parses_simple_move_line_path(self, handler, monkeypatch):
        """Should parse simple M L path commands."""
        # Mock path parsing
        mock_parse = Mock()
        start = Point(x=0, y=0)
        end = Point(x=100, y=100)
        segment = LineSegment(start=start, end=end)
        mock_parse.return_value = [segment]

        monkeypatch.setattr(
            "svg2ooxml.common.geometry.paths.parse_path_data",
            mock_parse,
        )

        result = handler._parse_motion_path("M0,0 L100,100")

        assert len(result) == 2
        assert result[0] == (0.0, 0.0)
        assert result[1] == (100.0, 100.0)

    def test_samples_bezier_curves(self, handler, monkeypatch):
        """Should sample bezier curves into line segments."""
        # Mock path parsing
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

        result = handler._parse_motion_path("M0,0 C50,0 50,100 100,100")

        # Should have start point + sampled points
        assert len(result) > 2  # More than just start/end
        assert result[0] == (0.0, 0.0)  # Start
        # Last point should be close to end (100, 100)
        assert abs(result[-1][0] - 100.0) < 1.0
        assert abs(result[-1][1] - 100.0) < 1.0

    def test_deduplicates_consecutive_points(self, handler, monkeypatch):
        """Should remove duplicate consecutive points."""
        # Mock path parsing to return duplicate points
        mock_parse = Mock()
        start = Point(x=0, y=0)
        mid = Point(x=0, y=0)  # Duplicate
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

        result = handler._parse_motion_path("M0,0 L0,0 L100,100")

        # Should deduplicate (0, 0)
        assert len(result) == 2
        assert result[0] == (0.0, 0.0)
        assert result[1] == (100.0, 100.0)

    def test_handles_path_parse_error(self, handler, monkeypatch):
        """Should return empty list on path parse error."""
        from svg2ooxml.common.geometry.paths import PathParseError

        mock_parse = Mock(side_effect=PathParseError("Invalid path"))
        monkeypatch.setattr(
            "svg2ooxml.common.geometry.paths.parse_path_data",
            mock_parse,
        )

        result = handler._parse_motion_path("INVALID")
        assert result == []

    def test_handles_import_error_with_fallback(self, handler, monkeypatch):
        """Should use fallback parser if imports fail."""
        # This test is tricky - we can't easily simulate import errors
        # Instead, test the fallback parser directly
        result = handler._simple_path_parse("M 0 0 L 100 100")
        assert len(result) == 2
        assert result[0] == (0.0, 0.0)
        assert result[1] == (100.0, 100.0)


class TestSampleBezier:
    """Tests for _sample_bezier method."""

    def test_samples_cubic_bezier_curve(self, handler):
        """Should sample cubic bezier curve at regular intervals."""
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

        result = handler._sample_bezier(segment, steps=10)

        # Should return 10 sample points
        assert len(result) == 10

        # All points should be Point objects
        assert all(isinstance(p, Point) for p in result)

        # Last point should be close to end point
        assert abs(result[-1].x - end.x) < 1.0
        assert abs(result[-1].y - end.y) < 1.0

    def test_samples_with_different_step_counts(self, handler):
        """Should respect steps parameter."""
        start = Point(x=0, y=0)
        control1 = Point(x=25, y=0)
        control2 = Point(x=75, y=100)
        end = Point(x=100, y=100)
        segment = BezierSegment(
            start=start,
            control1=control1,
            control2=control2,
            end=end,
        )

        result_5 = handler._sample_bezier(segment, steps=5)
        result_20 = handler._sample_bezier(segment, steps=20)

        assert len(result_5) == 5
        assert len(result_20) == 20


class TestBezierPoint:
    """Tests for _bezier_point method."""

    def test_returns_start_at_t_zero(self, handler):
        """Should return start point when t=0."""
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

        result = handler._bezier_point(segment, 0.0)

        assert abs(result.x - start.x) < 0.001
        assert abs(result.y - start.y) < 0.001

    def test_returns_end_at_t_one(self, handler):
        """Should return end point when t=1."""
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

        result = handler._bezier_point(segment, 1.0)

        assert abs(result.x - end.x) < 0.001
        assert abs(result.y - end.y) < 0.001

    def test_returns_midpoint_at_t_half(self, handler):
        """Should return point between start and end at t=0.5."""
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

        result = handler._bezier_point(segment, 0.5)

        # Should be somewhere in the middle
        assert 0 < result.x < 100
        assert 0 < result.y < 100


class TestDedupePoints:
    """Tests for _dedupe_points method."""

    def test_removes_exact_duplicates(self, handler):
        """Should remove consecutive exact duplicate points."""
        points = [
            Point(x=0, y=0),
            Point(x=0, y=0),
            Point(x=100, y=100),
        ]

        result = handler._dedupe_points(points)

        assert len(result) == 2
        assert result[0] == (0.0, 0.0)
        assert result[1] == (100.0, 100.0)

    def test_removes_near_duplicates(self, handler):
        """Should remove points within epsilon distance."""
        points = [
            Point(x=0, y=0),
            Point(x=0.0000001, y=0.0000001),  # Within epsilon
            Point(x=100, y=100),
        ]

        result = handler._dedupe_points(points)

        assert len(result) == 2

    def test_keeps_non_consecutive_duplicates(self, handler):
        """Should keep non-consecutive duplicate points."""
        points = [
            Point(x=0, y=0),
            Point(x=50, y=50),
            Point(x=0, y=0),  # Same as first, but not consecutive
        ]

        result = handler._dedupe_points(points)

        assert len(result) == 3

    def test_handles_empty_list(self, handler):
        """Should handle empty point list."""
        result = handler._dedupe_points([])
        assert result == []

    def test_handles_single_point(self, handler):
        """Should handle single point."""
        points = [Point(x=50, y=50)]
        result = handler._dedupe_points(points)
        assert result == [(50.0, 50.0)]


class TestSimplePathParse:
    """Tests for _simple_path_parse fallback method."""

    def test_parses_move_and_line_commands(self, handler):
        """Should parse M and L commands."""
        result = handler._simple_path_parse("M 0 0 L 100 100")
        assert len(result) == 2
        assert result[0] == (0.0, 0.0)
        assert result[1] == (100.0, 100.0)

    def test_handles_comma_separated_coords(self, handler):
        """Should handle comma-separated coordinates."""
        result = handler._simple_path_parse("M 0,0 L 100,100")
        assert len(result) == 2
        assert result[0] == (0.0, 0.0)
        assert result[1] == (100.0, 100.0)

    def test_handles_multiple_line_commands(self, handler):
        """Should parse multiple L commands."""
        result = handler._simple_path_parse("M 0 0 L 50 50 L 100 100")
        assert len(result) == 3
        assert result[0] == (0.0, 0.0)
        assert result[1] == (50.0, 50.0)
        assert result[2] == (100.0, 100.0)

    def test_ignores_unsupported_commands(self, handler):
        """Should skip unsupported path commands."""
        result = handler._simple_path_parse("M 0 0 C 50 0 50 100 100 100")
        # Should only get the M command point
        assert len(result) == 1
        assert result[0] == (0.0, 0.0)

    def test_handles_invalid_numbers(self, handler):
        """Should skip invalid numeric values."""
        result = handler._simple_path_parse("M invalid data L 100 100")
        # Should get the valid L command
        assert len(result) >= 1
        assert (100.0, 100.0) in result

    def test_handles_empty_string(self, handler):
        """Should return empty list for empty string."""
        result = handler._simple_path_parse("")
        assert result == []


class TestIntegration:
    """Integration tests combining multiple methods."""

    def test_complete_workflow_simple_path(self, handler, xml_builder, unit_converter):
        """Test complete workflow from animation to XML output."""
        animation = Mock(
            is_motion=True,
            values=["M0,0 L96,96"],  # 96px = 1 inch at 96 DPI
            duration_ms=2000,
            begin_ms=100,
            element_id="motion_shape",
        )

        # Handler should accept this animation
        assert handler.can_handle(animation) is True

        # Build XML
        result = handler.build(animation, par_id=10, behavior_id=20)

        # Verify XML structure
        assert result != ""
        xml_builder.build_behavior_core.assert_called_once_with(
            behavior_id=20,
            duration_ms=2000,
            target_shape="motion_shape",
        )

        xml_builder.build_par_container.assert_called_once()
        call_args = xml_builder.build_par_container.call_args
        assert call_args[1]["par_id"] == 10
        assert call_args[1]["delay_ms"] == 100

        # Verify points were converted
        assert unit_converter.to_emu.call_count >= 4  # 2 points × (x, y)

    def test_rejects_and_returns_empty_for_non_motion(self, handler):
        """Test rejection of non-motion animations."""
        animation = Mock(
            spec=["attribute_name", "values", "duration_ms"],
            attribute_name="opacity",
            values=["0", "1"],
            duration_ms=1000,
        )

        assert handler.can_handle(animation) is False
