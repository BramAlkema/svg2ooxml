"""Tests for SetAnimationHandler."""

from __future__ import annotations

import pytest
from lxml import etree

from svg2ooxml.common.units import UnitConverter
from svg2ooxml.drawingml.animation.handlers.set import SetAnimationHandler
from svg2ooxml.drawingml.animation.tav_builder import TAVBuilder
from svg2ooxml.drawingml.animation.value_processors import ValueProcessor
from svg2ooxml.drawingml.animation.xml_builders import AnimationXMLBuilder
from svg2ooxml.drawingml.xml_builder import NS_A, NS_P
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
)


def make_set_animation(**overrides) -> AnimationDefinition:
    """Build a real AnimationDefinition for set animations."""
    defaults = dict(
        element_id="shape1",
        animation_type=AnimationType.SET,
        target_attribute="visibility",
        values=["visible"],
        timing=AnimationTiming(begin=0.0, duration=0.001),
    )
    defaults.update(overrides)
    return AnimationDefinition(**defaults)


@pytest.fixture
def handler() -> SetAnimationHandler:
    xml = AnimationXMLBuilder()
    vp = ValueProcessor()
    tav = TAVBuilder(xml)
    uc = UnitConverter()
    return SetAnimationHandler(xml, vp, tav, uc)


# ------------------------------------------------------------------ #
# can_handle                                                          #
# ------------------------------------------------------------------ #


class TestCanHandle:
    def test_accepts_set(self, handler: SetAnimationHandler):
        anim = make_set_animation()
        assert handler.can_handle(anim) is True

    def test_rejects_animate(self, handler: SetAnimationHandler):
        anim = make_set_animation(animation_type=AnimationType.ANIMATE)
        assert handler.can_handle(anim) is False

    def test_rejects_animate_transform(self, handler: SetAnimationHandler):
        anim = make_set_animation(animation_type=AnimationType.ANIMATE_TRANSFORM)
        assert handler.can_handle(anim) is False


# ------------------------------------------------------------------ #
# _map_attribute_name                                                 #
# ------------------------------------------------------------------ #


class TestMapAttributeName:
    def test_maps_x(self, handler: SetAnimationHandler):
        assert handler._map_attribute_name("x") == "ppt_x"

    def test_maps_fill_color(self, handler: SetAnimationHandler):
        assert handler._map_attribute_name("fill") == "fill.color"

    def test_maps_stroke_color(self, handler: SetAnimationHandler):
        assert handler._map_attribute_name("stroke") == "stroke.color"

    def test_maps_visibility(self, handler: SetAnimationHandler):
        assert handler._map_attribute_name("visibility") == "style.visibility"

    def test_unmapped_passthrough(self, handler: SetAnimationHandler):
        assert handler._map_attribute_name("custom-attr") == "custom-attr"


# ------------------------------------------------------------------ #
# build — returns etree._Element                                      #
# ------------------------------------------------------------------ #


class TestBuild:
    def test_returns_element(self, handler: SetAnimationHandler):
        anim = make_set_animation()
        result = handler.build(anim, par_id=4, behavior_id=5)
        assert isinstance(result, etree._Element)
        assert result.tag == f"{{{NS_P}}}par"

    def test_empty_values_rejected_by_ir(self):
        """AnimationDefinition validates values is non-empty at construction."""
        with pytest.raises(ValueError, match="at least one value"):
            make_set_animation(values=[])

    def test_ctn_has_correct_id(self, handler: SetAnimationHandler):
        anim = make_set_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("id") == "4"

    def test_set_element_present(self, handler: SetAnimationHandler):
        anim = make_set_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        set_elem = par.find(f".//{{{NS_P}}}set")
        assert set_elem is not None

    def test_behavior_id(self, handler: SetAnimationHandler):
        anim = make_set_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        behavior_ids = {
            node.get("id")
            for node in par.findall(f".//{{{NS_P}}}cBhvr/{{{NS_P}}}cTn")
        }
        assert {"5", "6"} <= behavior_ids

    def test_target_shape(self, handler: SetAnimationHandler):
        anim = make_set_animation(element_id="shape42")
        par = handler.build(anim, par_id=4, behavior_id=5)
        sp_tgt = par.find(f".//{{{NS_P}}}spTgt")
        assert sp_tgt.get("spid") == "shape42"

    def test_numeric_set_has_strval(self, handler: SetAnimationHandler):
        anim = make_set_animation(
            target_attribute="visibility",
            values=["visible"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        str_val = par.find(f".//{{{NS_P}}}strVal")
        assert str_val is not None

    def test_color_set_has_srgbclr_in_clrval(self, handler: SetAnimationHandler):
        anim = make_set_animation(
            target_attribute="fill",
            values=["#ff0000"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        clr_val = par.find(f".//{{{NS_P}}}to/{{{NS_P}}}clrVal")
        assert clr_val is not None, "<p:to> must contain <p:clrVal> wrapper"
        srgb = clr_val.find(f"{{{NS_A}}}srgbClr")
        assert srgb is not None
        # parse_color normalizes to uppercase hex without #
        assert len(srgb.get("val")) == 6

    def test_uses_last_value(self, handler: SetAnimationHandler):
        anim = make_set_animation(
            target_attribute="visibility",
            values=["hidden", "visible"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        str_val = par.find(f".//{{{NS_P}}}strVal")
        assert str_val.get("val") == "visible"

    def test_delay_from_begin(self, handler: SetAnimationHandler):
        anim = make_set_animation(
            timing=AnimationTiming(begin=0.5, duration=0.001),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        cond = par.find(f".//{{{NS_P}}}cTn/{{{NS_P}}}stCondLst/{{{NS_P}}}cond")
        assert cond.get("delay") == "500"

    def test_attribute_name_mapped(self, handler: SetAnimationHandler):
        anim = make_set_animation(
            target_attribute="visibility",
            values=["hidden"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        attr_name = par.find(f".//{{{NS_P}}}attrName")
        assert attr_name.text == "style.visibility"

    def test_preset_class(self, handler: SetAnimationHandler):
        anim = make_set_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f".//{{{NS_P}}}cTn[@presetClass='entr']")
        assert ctn.get("presetClass") == "entr"
        assert ctn.get("presetID") == "1"
