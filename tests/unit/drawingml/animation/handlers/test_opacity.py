"""Tests for OpacityAnimationHandler."""

from __future__ import annotations

import pytest
from lxml import etree

from svg2ooxml.common.units import UnitConverter
from svg2ooxml.drawingml.animation.handlers.opacity import OpacityAnimationHandler
from svg2ooxml.drawingml.animation.tav_builder import TAVBuilder
from svg2ooxml.drawingml.animation.value_processors import ValueProcessor
from svg2ooxml.drawingml.animation.xml_builders import AnimationXMLBuilder
from svg2ooxml.drawingml.xml_builder import NS_P
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
)


def make_opacity_animation(**overrides) -> AnimationDefinition:
    """Build a real AnimationDefinition for opacity animations."""
    defaults = dict(
        element_id="shape1",
        animation_type=AnimationType.ANIMATE,
        target_attribute="opacity",
        values=["0", "1"],
        timing=AnimationTiming(begin=0.0, duration=1.0),
    )
    defaults.update(overrides)
    return AnimationDefinition(**defaults)


@pytest.fixture
def handler() -> OpacityAnimationHandler:
    xml = AnimationXMLBuilder()
    vp = ValueProcessor()
    tav = TAVBuilder(xml)
    uc = UnitConverter()
    return OpacityAnimationHandler(xml, vp, tav, uc)


# ------------------------------------------------------------------ #
# can_handle                                                          #
# ------------------------------------------------------------------ #


class TestCanHandle:
    def test_accepts_opacity(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation(target_attribute="opacity")
        assert handler.can_handle(anim) is True

    def test_accepts_fill_opacity(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation(target_attribute="fill-opacity")
        assert handler.can_handle(anim) is True

    def test_accepts_stroke_opacity(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation(target_attribute="stroke-opacity")
        assert handler.can_handle(anim) is True

    def test_rejects_fill(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation(target_attribute="fill")
        assert handler.can_handle(anim) is False

    def test_rejects_x(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation(target_attribute="x")
        assert handler.can_handle(anim) is False

    def test_rejects_non_animate_type(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation(animation_type=AnimationType.SET)
        assert handler.can_handle(anim) is False

    def test_rejects_animate_transform(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation(animation_type=AnimationType.ANIMATE_TRANSFORM)
        assert handler.can_handle(anim) is False


# ------------------------------------------------------------------ #
# build — returns etree._Element                                      #
# ------------------------------------------------------------------ #


class TestBuild:
    def test_returns_element(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation()
        result = handler.build(anim, par_id=4, behavior_id=5)
        assert isinstance(result, etree._Element)
        assert result.tag == f"{{{NS_P}}}par"

    def test_ctn_has_correct_id(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("id") == "4"

    def test_anim_effect_present(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_effect = par.find(f".//{{{NS_P}}}animEffect")
        assert anim_effect is not None

    def test_behavior_id(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        bhvr_ctn = par.find(f".//{{{NS_P}}}cBhvr/{{{NS_P}}}cTn")
        assert bhvr_ctn.get("id") == "5"

    def test_target_shape(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation(element_id="shape42")
        par = handler.build(anim, par_id=4, behavior_id=5)
        sp_tgt = par.find(f".//{{{NS_P}}}spTgt")
        assert sp_tgt.get("spid") == "shape42"

    def test_transition_attribute(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_effect = par.find(f".//{{{NS_P}}}animEffect")
        assert anim_effect.get("transition") == "in"

    def test_fade_opacity_value(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation(values=["0", "0.75"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_effect = par.find(f".//{{{NS_P}}}animEffect")
        assert "75000" in anim_effect.get("filter")

    def test_fade_in(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation(values=["0", "1"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_effect = par.find(f".//{{{NS_P}}}animEffect")
        assert "100000" in anim_effect.get("filter")

    def test_fade_out(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation(values=["1", "0"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_effect = par.find(f".//{{{NS_P}}}animEffect")
        assert anim_effect.get("filter") == "fade(opacity=0)"

    def test_delay_from_begin(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation(
            timing=AnimationTiming(begin=0.5, duration=1.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        cond = par.find(f".//{{{NS_P}}}cTn/{{{NS_P}}}stCondLst/{{{NS_P}}}cond")
        assert cond.get("delay") == "500"

    def test_duration(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation(
            timing=AnimationTiming(begin=0.0, duration=2.5),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("dur") == "2500"

    def test_preset_class(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("presetClass") == "entr"
