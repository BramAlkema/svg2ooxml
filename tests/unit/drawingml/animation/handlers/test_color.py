"""Tests for ColorAnimationHandler."""

from __future__ import annotations

import pytest
from lxml import etree

from svg2ooxml.common.units import UnitConverter
from svg2ooxml.drawingml.animation.handlers.color import ColorAnimationHandler
from svg2ooxml.drawingml.animation.tav_builder import TAVBuilder
from svg2ooxml.drawingml.animation.value_processors import ValueProcessor
from svg2ooxml.drawingml.animation.xml_builders import AnimationXMLBuilder
from svg2ooxml.drawingml.xml_builder import NS_A, NS_P
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    CalcMode,
)


def make_color_animation(**overrides) -> AnimationDefinition:
    """Build a real AnimationDefinition for color animations."""
    defaults = dict(
        element_id="shape1",
        animation_type=AnimationType.ANIMATE,
        target_attribute="fill",
        values=["#FF0000", "#00FF00"],
        timing=AnimationTiming(begin=0.0, duration=1.0),
    )
    defaults.update(overrides)
    return AnimationDefinition(**defaults)


@pytest.fixture
def handler() -> ColorAnimationHandler:
    xml = AnimationXMLBuilder()
    vp = ValueProcessor()
    tav = TAVBuilder(xml)
    uc = UnitConverter()
    return ColorAnimationHandler(xml, vp, tav, uc)


# ------------------------------------------------------------------ #
# can_handle                                                          #
# ------------------------------------------------------------------ #


class TestCanHandle:
    def test_accepts_fill(self, handler: ColorAnimationHandler):
        anim = make_color_animation(target_attribute="fill")
        assert handler.can_handle(anim) is True

    def test_accepts_stroke(self, handler: ColorAnimationHandler):
        anim = make_color_animation(target_attribute="stroke")
        assert handler.can_handle(anim) is True

    def test_accepts_stop_color(self, handler: ColorAnimationHandler):
        anim = make_color_animation(target_attribute="stop-color")
        assert handler.can_handle(anim) is True

    def test_accepts_stopcolor(self, handler: ColorAnimationHandler):
        anim = make_color_animation(target_attribute="stopcolor")
        assert handler.can_handle(anim) is True

    def test_accepts_flood_color(self, handler: ColorAnimationHandler):
        anim = make_color_animation(target_attribute="flood-color")
        assert handler.can_handle(anim) is True

    def test_accepts_lighting_color(self, handler: ColorAnimationHandler):
        anim = make_color_animation(target_attribute="lighting-color")
        assert handler.can_handle(anim) is True

    def test_accepts_animate_color_type(self, handler: ColorAnimationHandler):
        anim = make_color_animation(animation_type=AnimationType.ANIMATE_COLOR)
        assert handler.can_handle(anim) is True

    def test_rejects_opacity(self, handler: ColorAnimationHandler):
        anim = make_color_animation(target_attribute="opacity")
        assert handler.can_handle(anim) is False

    def test_rejects_x(self, handler: ColorAnimationHandler):
        anim = make_color_animation(target_attribute="x")
        assert handler.can_handle(anim) is False

    def test_rejects_transform(self, handler: ColorAnimationHandler):
        anim = make_color_animation(target_attribute="transform")
        assert handler.can_handle(anim) is False

    def test_rejects_set_type(self, handler: ColorAnimationHandler):
        anim = make_color_animation(animation_type=AnimationType.SET)
        assert handler.can_handle(anim) is False

    def test_rejects_animate_transform_type(self, handler: ColorAnimationHandler):
        anim = make_color_animation(animation_type=AnimationType.ANIMATE_TRANSFORM)
        assert handler.can_handle(anim) is False


# ------------------------------------------------------------------ #
# _map_color_attribute                                                #
# ------------------------------------------------------------------ #


class TestMapColorAttribute:
    def test_maps_fill(self, handler: ColorAnimationHandler):
        assert handler._map_color_attribute("fill") == "fillClr"

    def test_maps_stroke(self, handler: ColorAnimationHandler):
        assert handler._map_color_attribute("stroke") == "lnClr"

    def test_maps_stop_color(self, handler: ColorAnimationHandler):
        assert handler._map_color_attribute("stop-color") == "fillClr"

    def test_defaults_unknown(self, handler: ColorAnimationHandler):
        assert handler._map_color_attribute("unknown") == "fillClr"


# ------------------------------------------------------------------ #
# build — returns etree._Element                                      #
# ------------------------------------------------------------------ #


class TestBuild:
    def test_returns_element(self, handler: ColorAnimationHandler):
        anim = make_color_animation()
        result = handler.build(anim, par_id=4, behavior_id=5)
        assert isinstance(result, etree._Element)
        assert result.tag == f"{{{NS_P}}}par"

    def test_ctn_has_correct_id(self, handler: ColorAnimationHandler):
        anim = make_color_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("id") == "4"

    def test_ctn_uses_nonzero_effect_group(self, handler: ColorAnimationHandler):
        anim = make_color_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("grpId") == "4"

    def test_anim_clr_present(self, handler: ColorAnimationHandler):
        anim = make_color_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_clr = par.find(f".//{{{NS_P}}}animClr")
        assert anim_clr is not None

    def test_behavior_id(self, handler: ColorAnimationHandler):
        anim = make_color_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        bhvr_ctn = par.find(f".//{{{NS_P}}}cBhvr/{{{NS_P}}}cTn")
        assert bhvr_ctn.get("id") == "5"

    def test_target_shape(self, handler: ColorAnimationHandler):
        anim = make_color_animation(element_id="shape42")
        par = handler.build(anim, par_id=4, behavior_id=5)
        sp_tgt = par.find(f".//{{{NS_P}}}spTgt")
        assert sp_tgt.get("spid") == "shape42"

    def test_from_color(self, handler: ColorAnimationHandler):
        anim = make_color_animation(values=["#FF0000", "#00FF00"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        from_elem = par.find(f".//{{{NS_P}}}from")
        assert from_elem is not None
        srgb = from_elem.find(f"{{{NS_A}}}srgbClr")
        assert srgb is not None
        assert srgb.get("val") == "FF0000"

    def test_to_color(self, handler: ColorAnimationHandler):
        anim = make_color_animation(values=["#FF0000", "#00FF00"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        to_elem = par.find(f".//{{{NS_P}}}to")
        assert to_elem is not None
        srgb = to_elem.find(f"{{{NS_A}}}srgbClr")
        assert srgb is not None
        assert srgb.get("val") == "00FF00"

    def test_single_value_uses_same_for_from_and_to(
        self, handler: ColorAnimationHandler
    ):
        anim = make_color_animation(values=["#FF0000"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        from_srgb = par.find(f".//{{{NS_P}}}from/{{{NS_A}}}srgbClr")
        to_srgb = par.find(f".//{{{NS_P}}}to/{{{NS_A}}}srgbClr")
        assert from_srgb.get("val") == to_srgb.get("val")

    def test_attribute_name_mapped_fill(self, handler: ColorAnimationHandler):
        anim = make_color_animation(target_attribute="fill")
        par = handler.build(anim, par_id=4, behavior_id=5)
        attr_name = par.find(f".//{{{NS_P}}}attrName")
        assert attr_name.text == "fillClr"

    def test_attribute_name_mapped_stroke(self, handler: ColorAnimationHandler):
        anim = make_color_animation(target_attribute="stroke")
        par = handler.build(anim, par_id=4, behavior_id=5)
        attr_name = par.find(f".//{{{NS_P}}}attrName")
        assert attr_name.text == "lnClr"

    def test_delay_from_begin(self, handler: ColorAnimationHandler):
        anim = make_color_animation(
            timing=AnimationTiming(begin=0.5, duration=1.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        cond = par.find(f".//{{{NS_P}}}cTn/{{{NS_P}}}stCondLst/{{{NS_P}}}cond")
        assert cond.get("delay") == "500"

    def test_duration(self, handler: ColorAnimationHandler):
        anim = make_color_animation(
            timing=AnimationTiming(begin=0.0, duration=2.5),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("dur") == "2500"

    def test_preset_attrs_emphasis(self, handler: ColorAnimationHandler):
        """Color animations use emphasis preset for PowerPoint playback."""
        anim = make_color_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("presetClass") == "emph"
        assert ctn.get("presetID") == "7"

    def test_empty_values_rejected_by_ir(self):
        """AnimationDefinition validates values is non-empty at construction."""
        with pytest.raises(ValueError, match="at least one value"):
            make_color_animation(values=[])


# ------------------------------------------------------------------ #
# Multi-keyframe TAV list                                             #
# ------------------------------------------------------------------ #


class TestTAVList:
    def test_no_tav_for_two_values(self, handler: ColorAnimationHandler):
        anim = make_color_animation(values=["#FF0000", "#00FF00"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        tav_lst = par.find(f".//{{{NS_P}}}tavLst")
        assert tav_lst is None

    def test_multi_keyframe_values_emit_segmented_animclr(
        self, handler: ColorAnimationHandler
    ):
        anim = make_color_animation(values=["#FF0000", "#00FF00", "#0000FF"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        tav_lst = par.find(f".//{{{NS_P}}}tavLst")
        anim_clr = par.findall(f".//{{{NS_P}}}animClr")
        assert tav_lst is None
        assert len(anim_clr) == 2
        assert (
            par.xpath(
                "count(.//p:from/a:srgbClr[@val='FF0000'])",
                namespaces={"p": NS_P, "a": NS_A},
            )
            == 1.0
        )
        assert (
            par.xpath(
                "count(.//p:to/a:srgbClr[@val='00FF00'])",
                namespaces={"p": NS_P, "a": NS_A},
            )
            == 1.0
        )
        assert (
            par.xpath(
                "count(.//p:from/a:srgbClr[@val='00FF00'])",
                namespaces={"p": NS_P, "a": NS_A},
            )
            == 1.0
        )
        assert (
            par.xpath(
                "count(.//p:to/a:srgbClr[@val='0000FF'])",
                namespaces={"p": NS_P, "a": NS_A},
            )
            == 1.0
        )
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn is not None
        assert ctn.get("grpId") == "4"

    def test_explicit_key_times_split_delay_and_duration(
        self, handler: ColorAnimationHandler
    ):
        anim = make_color_animation(
            values=["#FF0000", "#00FF00"],
            key_times=[0.25, 1.0],
            timing=AnimationTiming(begin=0.0, duration=2.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        tav_lst = par.find(f".//{{{NS_P}}}tavLst")
        segment_ctn = par.find(
            f"./{{{NS_P}}}cTn/{{{NS_P}}}childTnLst/{{{NS_P}}}par/{{{NS_P}}}cTn"
        )
        assert tav_lst is None
        assert segment_ctn is not None
        assert segment_ctn.get("dur") == "1500"
        cond = segment_ctn.find(f"./{{{NS_P}}}stCondLst/{{{NS_P}}}cond")
        assert cond is not None
        assert cond.get("delay") == "500"

    def test_discrete_calc_mode_emits_color_set_steps(
        self, handler: ColorAnimationHandler
    ):
        anim = make_color_animation(
            values=["#FF0000", "#00FF00", "#0000FF"],
            key_times=[0.0, 0.4, 1.0],
            calc_mode=CalcMode.DISCRETE,
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        tav_lst = par.find(f".//{{{NS_P}}}tavLst")
        set_elems = par.findall(f".//{{{NS_P}}}set")
        anim_clr = par.findall(f".//{{{NS_P}}}animClr")
        assert tav_lst is None
        assert len(set_elems) == 3
        assert not anim_clr
        assert (
            par.xpath(
                "count(.//p:to/p:clrVal/a:srgbClr[@val='FF0000'])",
                namespaces={"p": NS_P, "a": NS_A},
            )
            == 1.0
        )
        assert (
            par.xpath(
                "count(.//p:to/p:clrVal/a:srgbClr[@val='00FF00'])",
                namespaces={"p": NS_P, "a": NS_A},
            )
            == 1.0
        )
        assert (
            par.xpath(
                "count(.//p:to/p:clrVal/a:srgbClr[@val='0000FF'])",
                namespaces={"p": NS_P, "a": NS_A},
            )
            == 1.0
        )
