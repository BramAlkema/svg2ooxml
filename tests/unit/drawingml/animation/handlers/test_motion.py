"""Tests for MotionAnimationHandler."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from lxml import etree

from svg2ooxml.common.geometry.paths.segments import BezierSegment, LineSegment
from svg2ooxml.common.units import UnitConverter
from svg2ooxml.drawingml.animation.handlers.motion import MotionAnimationHandler
from svg2ooxml.drawingml.animation.tav_builder import TAVBuilder
from svg2ooxml.drawingml.animation.value_processors import ValueProcessor
from svg2ooxml.drawingml.animation.xml_builders import AnimationXMLBuilder
from svg2ooxml.drawingml.xml_builder import NS_P
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
)
from svg2ooxml.ir.geometry import Point


def make_motion_animation(**overrides) -> AnimationDefinition:
    """Build a real AnimationDefinition for motion animations."""
    defaults = dict(
        element_id="shape1",
        animation_type=AnimationType.ANIMATE_MOTION,
        target_attribute="d",
        values=["M0,0 L100,100"],
        timing=AnimationTiming(begin=0.0, duration=1.0),
    )
    defaults.update(overrides)
    return AnimationDefinition(**defaults)


@pytest.fixture
def handler() -> MotionAnimationHandler:
    xml = AnimationXMLBuilder()
    vp = ValueProcessor()
    tav = TAVBuilder(xml)
    uc = UnitConverter()
    return MotionAnimationHandler(xml, vp, tav, uc)


# ------------------------------------------------------------------ #
# can_handle                                                          #
# ------------------------------------------------------------------ #


class TestCanHandle:
    def test_accepts_animate_motion(self, handler: MotionAnimationHandler):
        anim = make_motion_animation()
        assert handler.can_handle(anim) is True

    def test_rejects_animate(self, handler: MotionAnimationHandler):
        anim = make_motion_animation(animation_type=AnimationType.ANIMATE)
        assert handler.can_handle(anim) is False

    def test_rejects_set(self, handler: MotionAnimationHandler):
        anim = make_motion_animation(animation_type=AnimationType.SET)
        assert handler.can_handle(anim) is False

    def test_rejects_animate_transform(self, handler: MotionAnimationHandler):
        anim = make_motion_animation(animation_type=AnimationType.ANIMATE_TRANSFORM)
        assert handler.can_handle(anim) is False

    def test_rejects_animate_color(self, handler: MotionAnimationHandler):
        anim = make_motion_animation(animation_type=AnimationType.ANIMATE_COLOR)
        assert handler.can_handle(anim) is False


# ------------------------------------------------------------------ #
# build — returns etree._Element                                      #
# ------------------------------------------------------------------ #


class TestBuild:
    def test_returns_element(self, handler: MotionAnimationHandler):
        anim = make_motion_animation()
        result = handler.build(anim, par_id=4, behavior_id=5)
        assert isinstance(result, etree._Element)
        assert result.tag == f"{{{NS_P}}}par"

    def test_returns_none_for_single_point_path(self, handler: MotionAnimationHandler):
        anim = make_motion_animation(values=["M0,0"])
        result = handler.build(anim, par_id=4, behavior_id=5)
        assert result is None

    def test_ctn_has_correct_id(self, handler: MotionAnimationHandler):
        anim = make_motion_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("id") == "4"

    def test_anim_motion_present(self, handler: MotionAnimationHandler):
        anim = make_motion_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        assert anim_motion is not None

    def test_anim_motion_attributes(self, handler: MotionAnimationHandler):
        anim = make_motion_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        assert anim_motion.get("origin") == "layout"
        assert anim_motion.get("pathEditMode") == "relative"
        assert anim_motion.get("rAng") == "0"

    def test_anim_motion_auto_rotate_sets_non_zero_rang(self, handler: MotionAnimationHandler):
        anim = make_motion_animation(
            values=["M0,0 L0,100"],
            motion_rotate="auto",
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        assert anim_motion.get("rAng") == "5400000"

    def test_behavior_id(self, handler: MotionAnimationHandler):
        anim = make_motion_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        bhvr_ctn = par.find(f".//{{{NS_P}}}cBhvr/{{{NS_P}}}cTn")
        assert bhvr_ctn.get("id") == "5"

    def test_target_shape(self, handler: MotionAnimationHandler):
        anim = make_motion_animation(element_id="motion_shape")
        par = handler.build(anim, par_id=4, behavior_id=5)
        sp_tgt = par.find(f".//{{{NS_P}}}spTgt")
        assert sp_tgt.get("spid") == "motion_shape"

    def test_attr_name_list(self, handler: MotionAnimationHandler):
        anim = make_motion_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        attr_names = par.findall(f".//{{{NS_P}}}attrName")
        texts = [a.text for a in attr_names]
        assert "ppt_x" in texts
        assert "ppt_y" in texts

    def test_rotation_center(self, handler: MotionAnimationHandler):
        anim = make_motion_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        rctr = par.find(f".//{{{NS_P}}}rCtr")
        assert rctr is not None
        assert rctr.get("x") == "4306"
        assert rctr.get("y") == "0"

    def test_preset_class_is_path(self, handler: MotionAnimationHandler):
        anim = make_motion_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("presetClass") == "path"

    def test_delay_from_begin(self, handler: MotionAnimationHandler):
        anim = make_motion_animation(
            timing=AnimationTiming(begin=0.5, duration=1.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        cond = par.find(f".//{{{NS_P}}}cTn/{{{NS_P}}}stCondLst/{{{NS_P}}}cond")
        assert cond.get("delay") == "500"

    def test_path_attribute_contains_m_and_l(self, handler: MotionAnimationHandler):
        anim = make_motion_animation(values=["M0,0 L100,100"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        path = anim_motion.get("path")
        assert path.startswith("M ")
        assert " L " in path


# ------------------------------------------------------------------ #
# Path parsing helpers                                                #
# ------------------------------------------------------------------ #


class TestParseMotionPath:
    def test_returns_empty_for_empty_path(self, handler: MotionAnimationHandler):
        assert handler._parse_motion_path("") == []

    def test_parses_simple_move_line_path(self, handler: MotionAnimationHandler, monkeypatch):
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

    def test_samples_bezier_curves(self, handler: MotionAnimationHandler, monkeypatch):
        mock_parse = Mock()
        start = Point(x=0, y=0)
        control1 = Point(x=50, y=0)
        control2 = Point(x=50, y=100)
        end = Point(x=100, y=100)
        segment = BezierSegment(start=start, control1=control1, control2=control2, end=end)
        mock_parse.return_value = [segment]
        monkeypatch.setattr(
            "svg2ooxml.common.geometry.paths.parse_path_data",
            mock_parse,
        )
        result = handler._parse_motion_path("M0,0 C50,0 50,100 100,100")
        assert len(result) > 2
        assert result[0] == (0.0, 0.0)
        assert abs(result[-1][0] - 100.0) < 1.0
        assert abs(result[-1][1] - 100.0) < 1.0

    def test_deduplicates_consecutive_points(self, handler: MotionAnimationHandler, monkeypatch):
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
        result = handler._parse_motion_path("M0,0 L0,0 L100,100")
        assert len(result) == 2

    def test_handles_path_parse_error(self, handler: MotionAnimationHandler, monkeypatch):
        from svg2ooxml.common.geometry.paths import PathParseError

        mock_parse = Mock(side_effect=PathParseError("Invalid path"))
        monkeypatch.setattr(
            "svg2ooxml.common.geometry.paths.parse_path_data",
            mock_parse,
        )
        result = handler._parse_motion_path("INVALID")
        assert result == []


class TestSampleBezier:
    def test_samples_cubic_bezier_curve(self, handler: MotionAnimationHandler):
        segment = BezierSegment(
            start=Point(x=0, y=0),
            control1=Point(x=50, y=0),
            control2=Point(x=50, y=100),
            end=Point(x=100, y=100),
        )
        result = handler._sample_bezier(segment, steps=10)
        assert len(result) == 10
        assert all(isinstance(p, Point) for p in result)
        assert abs(result[-1].x - 100.0) < 1.0
        assert abs(result[-1].y - 100.0) < 1.0


class TestBezierPoint:
    def test_returns_start_at_t_zero(self, handler: MotionAnimationHandler):
        segment = BezierSegment(
            start=Point(x=0, y=0),
            control1=Point(x=50, y=0),
            control2=Point(x=50, y=100),
            end=Point(x=100, y=100),
        )
        result = handler._bezier_point(segment, 0.0)
        assert abs(result.x) < 0.001
        assert abs(result.y) < 0.001

    def test_returns_end_at_t_one(self, handler: MotionAnimationHandler):
        segment = BezierSegment(
            start=Point(x=0, y=0),
            control1=Point(x=50, y=0),
            control2=Point(x=50, y=100),
            end=Point(x=100, y=100),
        )
        result = handler._bezier_point(segment, 1.0)
        assert abs(result.x - 100.0) < 0.001
        assert abs(result.y - 100.0) < 0.001


class TestDedupePoints:
    def test_removes_exact_duplicates(self, handler: MotionAnimationHandler):
        points = [Point(x=0, y=0), Point(x=0, y=0), Point(x=100, y=100)]
        result = handler._dedupe_points(points)
        assert len(result) == 2

    def test_keeps_non_consecutive_duplicates(self, handler: MotionAnimationHandler):
        points = [Point(x=0, y=0), Point(x=50, y=50), Point(x=0, y=0)]
        result = handler._dedupe_points(points)
        assert len(result) == 3

    def test_handles_empty_list(self, handler: MotionAnimationHandler):
        assert handler._dedupe_points([]) == []


class TestSimplePathParse:
    def test_parses_move_and_line(self, handler: MotionAnimationHandler):
        result = handler._simple_path_parse("M 0 0 L 100 100")
        assert len(result) == 2
        assert result[0] == (0.0, 0.0)
        assert result[1] == (100.0, 100.0)

    def test_handles_comma_separated(self, handler: MotionAnimationHandler):
        result = handler._simple_path_parse("M 0,0 L 100,100")
        assert len(result) == 2

    def test_handles_multiple_lines(self, handler: MotionAnimationHandler):
        result = handler._simple_path_parse("M 0 0 L 50 50 L 100 100")
        assert len(result) == 3

    def test_handles_empty_string(self, handler: MotionAnimationHandler):
        assert handler._simple_path_parse("") == []
