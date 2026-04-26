"""Tests for MotionAnimationHandler."""

from __future__ import annotations

import pytest
from lxml import etree

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
    CalcMode,
)


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

    def test_ctn_uses_nonzero_effect_group(self, handler: MotionAnimationHandler):
        anim = make_motion_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("grpId") == "4"

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
        assert anim_motion.get("rAng") is None

    def test_anim_motion_auto_rotate_sets_non_zero_rang(
        self, handler: MotionAnimationHandler
    ):
        anim = make_motion_animation(
            values=["M0,0 L0,100"],
            motion_rotate="auto",
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        assert anim_motion.get("rAng") == "5400000"

    def test_anim_motion_auto_rotate_turn_emits_stacked_anim_rot(
        self, handler: MotionAnimationHandler
    ):
        anim = make_motion_animation(
            values=["M0,0 L100,0 L100,100"],
            motion_rotate="auto",
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        rots = par.findall(f".//{{{NS_P}}}animRot")

        assert anim_motion.get("rAng") is None
        assert len(rots) == 1
        assert rots[0].get("by") == "5400000"

    def test_anim_motion_auto_reverse_turn_keeps_initial_flip(
        self, handler: MotionAnimationHandler
    ):
        anim = make_motion_animation(
            values=["M0,0 L100,0 L100,100"],
            motion_rotate="auto-reverse",
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        rots = par.findall(f".//{{{NS_P}}}animRot")

        assert anim_motion.get("rAng") is None
        assert len(rots) == 2
        assert rots[0].get("by") == "10800000"
        assert rots[1].get("by") == "5400000"

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

    def test_does_not_emit_attr_name_list(self, handler: MotionAnimationHandler):
        anim = make_motion_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        attr_names = par.findall(f".//{{{NS_P}}}attrName")
        assert not attr_names

    def test_does_not_emit_rotation_center_child(self, handler: MotionAnimationHandler):
        anim = make_motion_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        rctr = par.find(f".//{{{NS_P}}}rCtr")
        assert rctr is None

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
        assert path.endswith(" E")

    def test_discrete_calc_mode_expands_step_path(
        self, handler: MotionAnimationHandler
    ):
        anim = make_motion_animation(
            values=["M0,0 L100,0"],
            key_times=[0.0, 0.4, 1.0],
            calc_mode=CalcMode.DISCRETE,
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        path = anim_motion.get("path")
        assert path.count("L ") > 1
        assert path.endswith(" E")

    def test_paced_calc_mode_with_key_times_retimes_path(
        self, handler: MotionAnimationHandler
    ):
        anim = make_motion_animation(
            values=["M0,0 L10,0 L40,0"],
            key_times=[0.0, 0.9, 1.0],
            calc_mode=CalcMode.PACED,
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        path = anim_motion.get("path")
        assert path is not None
        assert path.count("L ") > 2

    def test_auto_rotate_uses_element_heading_for_dynamic_curve(
        self, handler: MotionAnimationHandler
    ):
        anim = make_motion_animation(
            values=["M25,225 C25,175 125,150 175,200"],
            timing=AnimationTiming(begin=0.0, duration=6.0),
            motion_rotate="auto",
            motion_viewport_px=(480.0, 360.0),
            element_heading_deg=-90.0,
        )

        par = handler.build(anim, par_id=4, behavior_id=5)
        rots = par.findall(f".//{{{NS_P}}}animRot")
        first_rot_ctn = par.find(
            f".//{{{NS_P}}}childTnLst/{{{NS_P}}}par/{{{NS_P}}}cTn"
        )

        assert rots
        assert first_rot_ctn is not None
        assert first_rot_ctn.get("dur") != "1"
