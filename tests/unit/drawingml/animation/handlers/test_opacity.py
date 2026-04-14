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
    CalcMode,
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

    def test_partial_fade_uses_property_animation(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation(values=["0", "0.75"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        assert par.find(f".//{{{NS_P}}}animEffect") is None
        anim_elem = par.find(f".//{{{NS_P}}}anim")
        assert anim_elem is not None
        attr_name = par.find(f".//{{{NS_P}}}attrName")
        assert attr_name is not None
        assert attr_name.text == "style.opacity"

    def test_fill_opacity_maps_to_fill_opacity_property(
        self, handler: OpacityAnimationHandler
    ):
        anim = make_opacity_animation(target_attribute="fill-opacity")
        par = handler.build(anim, par_id=4, behavior_id=5)
        attr_name = par.find(f".//{{{NS_P}}}attrName")
        assert attr_name is not None
        assert attr_name.text == "fill.opacity"

    def test_stroke_opacity_maps_to_stroke_opacity_property(
        self, handler: OpacityAnimationHandler
    ):
        anim = make_opacity_animation(target_attribute="stroke-opacity")
        par = handler.build(anim, par_id=4, behavior_id=5)
        attr_name = par.find(f".//{{{NS_P}}}attrName")
        assert attr_name is not None
        assert attr_name.text == "stroke.opacity"

    def test_fade_in(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation(values=["0", "1"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_effect = par.find(f".//{{{NS_P}}}animEffect")
        assert anim_effect.get("filter") == "fade"

    def test_fade_out(self, handler: OpacityAnimationHandler):
        anim = make_opacity_animation(values=["1", "0"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_effect = par.find(f".//{{{NS_P}}}animEffect")
        assert anim_effect is not None
        assert anim_effect.get("transition") == "out"
        assert anim_effect.get("filter") == "fade"
        assert par.find(f".//{{{NS_P}}}anim") is None
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn is not None
        assert ctn.get("presetClass") == "exit"

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

    def test_nonzero_start_opacity_uses_property_animation(
        self, handler: OpacityAnimationHandler
    ):
        anim = make_opacity_animation(values=["0.1", "1"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        assert par.find(f".//{{{NS_P}}}animEffect") is None
        anim_elem = par.find(f".//{{{NS_P}}}anim")
        assert anim_elem is not None
        attr_name = par.find(f".//{{{NS_P}}}attrName")
        assert attr_name.text == "style.opacity"

    def test_multi_keyframe_opacity_uses_transparency_effect(
        self, handler: OpacityAnimationHandler
    ):
        anim = make_opacity_animation(values=["0.1", "1", "0.1"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_effect = par.find(f".//{{{NS_P}}}animEffect")
        assert anim_effect is not None
        assert anim_effect.get("filter") == "image"
        assert anim_effect.get("prLst") == "opacity: 1"
        assert par.find(f".//{{{NS_P}}}anim") is None
        set_elem = par.find(f".//{{{NS_P}}}set")
        assert set_elem is not None
        str_val = set_elem.find(f".//{{{NS_P}}}strVal")
        assert str_val is not None
        assert str_val.get("val") == "0.1"
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn is not None
        assert ctn.get("presetSubtype") == "0"
        assert ctn.get("autoRev") is None
        effect_cbhvr = anim_effect.find(f"{{{NS_P}}}cBhvr")
        assert effect_cbhvr is not None
        assert effect_cbhvr.get("rctx") == "IE"
        effect_ctn = effect_cbhvr.find(f"{{{NS_P}}}cTn")
        assert effect_ctn is not None
        assert effect_ctn.get("autoRev") == "1"

    def test_opacity_pulse_preserves_authored_direction(
        self, handler: OpacityAnimationHandler
    ):
        anim = make_opacity_animation(values=["1", "0", "1"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_effect = par.find(f".//{{{NS_P}}}animEffect")
        assert anim_effect is not None
        assert anim_effect.get("prLst") == "opacity: 0"
        set_elem = par.find(f".//{{{NS_P}}}set")
        assert set_elem is not None
        str_val = set_elem.find(f".//{{{NS_P}}}strVal")
        assert str_val is not None
        assert str_val.get("val") == "1"

    def test_repeat_opacity_uses_property_animation(
        self, handler: OpacityAnimationHandler
    ):
        anim = make_opacity_animation(
            values=["0", "1"],
            timing=AnimationTiming(begin=0.0, duration=1.0, repeat_count="indefinite"),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        assert par.find(f".//{{{NS_P}}}animEffect") is None
        assert par.find(f".//{{{NS_P}}}anim") is not None

    def test_spline_opacity_uses_property_animation_and_dense_tavs(
        self, handler: OpacityAnimationHandler
    ):
        anim = make_opacity_animation(
            values=["0", "1"],
            calc_mode=CalcMode.SPLINE,
            key_splines=[[0.75, 0.0, 0.25, 1.0]],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        assert par.find(f".//{{{NS_P}}}animEffect") is None
        anim_elem = par.find(f".//{{{NS_P}}}anim")
        assert anim_elem is not None
        tavs = par.findall(f".//{{{NS_P}}}tav")
        assert len(tavs) > 2
