"""Tests for NumericAnimationHandler."""

from __future__ import annotations

import pytest
from lxml import etree

from svg2ooxml.common.units import UnitConverter
from svg2ooxml.drawingml.animation.handlers.numeric import NumericAnimationHandler
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


def make_numeric_animation(**overrides) -> AnimationDefinition:
    """Build a real AnimationDefinition for numeric animations.

    Uses stroke-width as default attribute to test the generic <p:anim> path.
    Use target_attribute="x" or "width" to test motion/scale paths.
    """
    defaults = dict(
        element_id="shape1",
        animation_type=AnimationType.ANIMATE,
        target_attribute="stroke-width",
        values=["0", "100"],
        timing=AnimationTiming(begin=0.0, duration=1.0),
    )
    defaults.update(overrides)
    return AnimationDefinition(**defaults)


@pytest.fixture
def handler() -> NumericAnimationHandler:
    xml = AnimationXMLBuilder()
    vp = ValueProcessor()
    tav = TAVBuilder(xml)
    uc = UnitConverter()
    return NumericAnimationHandler(xml, vp, tav, uc)


# ------------------------------------------------------------------ #
# can_handle                                                          #
# ------------------------------------------------------------------ #


class TestCanHandle:
    def test_accepts_x(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(target_attribute="x")
        assert handler.can_handle(anim) is True

    def test_accepts_y(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(target_attribute="y")
        assert handler.can_handle(anim) is True

    def test_accepts_width(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(target_attribute="width")
        assert handler.can_handle(anim) is True

    def test_accepts_height(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(target_attribute="height")
        assert handler.can_handle(anim) is True

    def test_rejects_line_endpoint_attributes(self, handler: NumericAnimationHandler):
        for attr in ("x1", "x2", "y1", "y2"):
            anim = make_numeric_animation(target_attribute=attr)
            assert handler.can_handle(anim) is False

    def test_accepts_stroke_width(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(target_attribute="stroke-width")
        assert handler.can_handle(anim) is True

    def test_accepts_rotate(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(target_attribute="rotate")
        assert handler.can_handle(anim) is True

    def test_rejects_opacity(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(target_attribute="opacity")
        assert handler.can_handle(anim) is False

    def test_rejects_fill_opacity(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(target_attribute="fill-opacity")
        assert handler.can_handle(anim) is False

    def test_rejects_fill_color(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(target_attribute="fill")
        assert handler.can_handle(anim) is False

    def test_rejects_stroke_color(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(target_attribute="stroke")
        assert handler.can_handle(anim) is False

    def test_rejects_display(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(target_attribute="display")
        assert handler.can_handle(anim) is False

    def test_rejects_visibility(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(target_attribute="visibility")
        assert handler.can_handle(anim) is False

    def test_rejects_style_visibility(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(target_attribute="style.visibility")
        assert handler.can_handle(anim) is False

    def test_rejects_set_type(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(animation_type=AnimationType.SET)
        assert handler.can_handle(anim) is False

    def test_rejects_animate_transform(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(animation_type=AnimationType.ANIMATE_TRANSFORM)
        assert handler.can_handle(anim) is False

    def test_rejects_animate_motion(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(animation_type=AnimationType.ANIMATE_MOTION)
        assert handler.can_handle(anim) is False


# ------------------------------------------------------------------ #
# _map_attribute_name                                                 #
# ------------------------------------------------------------------ #


class TestMapAttributeName:
    def test_maps_x(self, handler: NumericAnimationHandler):
        assert handler._map_attribute_name("x") == "ppt_x"

    def test_maps_y(self, handler: NumericAnimationHandler):
        assert handler._map_attribute_name("y") == "ppt_y"

    def test_maps_width(self, handler: NumericAnimationHandler):
        assert handler._map_attribute_name("width") == "ppt_w"

    def test_maps_height(self, handler: NumericAnimationHandler):
        assert handler._map_attribute_name("height") == "ppt_h"

    def test_maps_rotate(self, handler: NumericAnimationHandler):
        assert handler._map_attribute_name("rotate") == "ppt_angle"

    def test_maps_stroke_width(self, handler: NumericAnimationHandler):
        assert handler._map_attribute_name("stroke-width") == "stroke.weight"

    def test_unmapped_passthrough(self, handler: NumericAnimationHandler):
        assert handler._map_attribute_name("custom-attr") == "custom-attr"


# ------------------------------------------------------------------ #
# build — returns etree._Element                                      #
# ------------------------------------------------------------------ #


class TestBuild:
    def test_returns_element(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation()
        result = handler.build(anim, par_id=4, behavior_id=5)
        assert isinstance(result, etree._Element)
        assert result.tag == f"{{{NS_P}}}par"

    def test_ctn_has_correct_id(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("id") == "4"

    def test_anim_element_present(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_elem = par.find(f".//{{{NS_P}}}anim")
        assert anim_elem is not None

    def test_behavior_id(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        bhvr_ctn = par.find(f".//{{{NS_P}}}cBhvr/{{{NS_P}}}cTn")
        assert bhvr_ctn.get("id") == "5"

    def test_target_shape(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(element_id="shape42")
        par = handler.build(anim, par_id=4, behavior_id=5)
        sp_tgt = par.find(f".//{{{NS_P}}}spTgt")
        assert sp_tgt.get("spid") == "shape42"

    def test_attribute_name_mapped(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(target_attribute="stroke-width")
        par = handler.build(anim, par_id=4, behavior_id=5)
        attr_name = par.find(f".//{{{NS_P}}}attrName")
        assert attr_name.text == "stroke.weight"

    def test_tav_list_present(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        tav_lst = par.find(f".//{{{NS_P}}}tavLst")
        assert tav_lst is not None

    def test_simple_from_to_tav_entries(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(values=["0", "100"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        tavs = par.findall(f".//{{{NS_P}}}tav")
        assert len(tavs) == 2
        assert tavs[0].get("tm") == "0"
        assert tavs[1].get("tm") == "100000"

    def test_simple_non_numeric_values_use_strval(
        self, handler: NumericAnimationHandler
    ):
        anim = make_numeric_animation(
            target_attribute="custom-state", values=["visible", "hidden"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        flt_vals = par.findall(f".//{{{NS_P}}}fltVal")
        str_vals = par.findall(f".//{{{NS_P}}}strVal")
        assert not flt_vals
        assert [node.get("val") for node in str_vals] == ["visible", "hidden"]

    def test_delay_from_begin(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(
            timing=AnimationTiming(begin=0.5, duration=1.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        cond = par.find(f".//{{{NS_P}}}cTn/{{{NS_P}}}stCondLst/{{{NS_P}}}cond")
        assert cond.get("delay") == "500"

    def test_duration(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(
            timing=AnimationTiming(begin=0.0, duration=2.5),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("dur") == "2500"

    def test_preset_attrs_emphasis(self, handler: NumericAnimationHandler):
        """Numeric animations use emphasis preset for PowerPoint playback."""
        anim = make_numeric_animation()
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("presetClass") == "emph"
        assert ctn.get("presetID") == "32"

    def test_simple_width_animation_uses_authored_by_scale(
        self, handler: NumericAnimationHandler
    ):
        anim = make_numeric_animation(target_attribute="width", values=["10", "20"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_scale = par.find(f".//{{{NS_P}}}animScale")
        assert anim_scale is not None
        by_elem = anim_scale.find(f"{{{NS_P}}}by")
        assert by_elem is not None
        assert by_elem.get("x") == "200000"
        assert by_elem.get("y") == "100000"
        assert not par.findall(f".//{{{NS_P}}}attrName")

    def test_position_animation_projects_delta_through_motion_space_matrix(
        self, handler: NumericAnimationHandler
    ):
        anim = make_numeric_animation(
            target_attribute="x",
            values=["0", "100"],
            motion_viewport_px=(1000.0, 1000.0),
            motion_space_matrix=(2.0, 0.0, 0.0, 3.0, 50.0, 90.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        motion = par.find(f".//{{{NS_P}}}animMotion")
        assert motion is not None
        assert motion.get("path") == "M 0 0 L 0.200000 0.000000 E"

    def test_scale_anchor_motion_projects_delta_through_motion_space_matrix(
        self, handler: NumericAnimationHandler
    ):
        anim = make_numeric_animation(
            target_attribute="height",
            values=["20", "40"],
            motion_viewport_px=(1000.0, 1000.0),
            motion_space_matrix=(2.0, 0.0, 0.0, 3.0, 50.0, 90.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        motions = par.findall(f".//{{{NS_P}}}animMotion")
        assert len(motions) == 1
        assert motions[0].get("path") == "M 0 0 L 0.000000 0.030000 E"

    def test_symmetric_multi_keyframe_width_animation_uses_autoreverse_scale(
        self, handler: NumericAnimationHandler
    ):
        anim = make_numeric_animation(
            target_attribute="width",
            values=["10", "40", "10"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_scale = par.find(f".//{{{NS_P}}}animScale")
        assert anim_scale is not None
        assert par.find(f".//{{{NS_P}}}anim") is None
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn is not None
        assert ctn.get("presetSubtype") == "0"
        bhvr_ctn = par.find(f".//{{{NS_P}}}cBhvr/{{{NS_P}}}cTn")
        assert bhvr_ctn is not None
        assert bhvr_ctn.get("dur") == "500"
        assert bhvr_ctn.get("autoRev") == "1"
        assert bhvr_ctn.get("repeatCount") is None
        assert not par.findall(f".//{{{NS_P}}}attrName")
        by_elem = anim_scale.find(f"{{{NS_P}}}by")
        assert by_elem is not None
        assert by_elem.get("x") == "400000"
        assert by_elem.get("y") == "100000"

    def test_multi_keyframe_width_animation_with_custom_key_times_uses_segmented_anim_scale(
        self, handler: NumericAnimationHandler
    ):
        anim = make_numeric_animation(
            target_attribute="width",
            values=["10", "40", "10"],
            key_times=[0.0, 0.3, 1.0],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_scales = par.findall(f".//{{{NS_P}}}animScale")
        assert len(anim_scales) == 2
        assert par.find(f".//{{{NS_P}}}anim") is None
        assert not par.findall(f".//{{{NS_P}}}tav")
        attr_names = [node.text for node in par.findall(f".//{{{NS_P}}}attrName")]
        assert "ppt_w" not in attr_names
        assert "ScaleX" not in attr_names
        assert "ScaleY" not in attr_names
        assert anim_scales[0].find(f"{{{NS_P}}}by").get("x") == "400000"
        assert anim_scales[0].find(f"{{{NS_P}}}by").get("y") == "100000"
        assert anim_scales[1].find(f"{{{NS_P}}}by").get("x") == "25000"
        assert anim_scales[1].find(f"{{{NS_P}}}by").get("y") == "100000"

    def test_position_animation_uses_relative_delta_path(
        self, handler: NumericAnimationHandler
    ):
        anim = make_numeric_animation(
            target_attribute="x",
            values=["20", "30"],
            motion_viewport_px=(480.0, 360.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        assert anim_motion is not None
        path = anim_motion.get("path")
        assert path.startswith("M 0 0 L ")
        assert "0.020833" in path

    def test_height_animation_anchor_motion_uses_scene_viewport(
        self, handler: NumericAnimationHandler
    ):
        anim = make_numeric_animation(
            target_attribute="height",
            values=["20", "40"],
            motion_viewport_px=(480.0, 360.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        motions = par.findall(f".//{{{NS_P}}}animMotion")
        assert len(motions) == 1
        assert motions[0].get("path") == "M 0 0 L 0.000000 0.027778 E"

    def test_empty_values_rejected_by_ir(self):
        """AnimationDefinition validates values is non-empty at construction."""
        with pytest.raises(ValueError, match="at least one value"):
            make_numeric_animation(values=[])


# ------------------------------------------------------------------ #
# Multi-keyframe TAV list                                             #
# ------------------------------------------------------------------ #


class TestMultiKeyframe:
    def test_three_values_produce_three_tavs(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(values=["0", "50", "100"])
        par = handler.build(anim, par_id=4, behavior_id=5)
        tavs = par.findall(f".//{{{NS_P}}}tav")
        assert len(tavs) == 3

    def test_explicit_key_times(self, handler: NumericAnimationHandler):
        anim = make_numeric_animation(
            values=["0", "50", "100"],
            key_times=[0.0, 0.3, 1.0],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        tavs = par.findall(f".//{{{NS_P}}}tav")
        assert len(tavs) == 3

    def test_discrete_calc_mode_emits_set_segments(self, handler: NumericAnimationHandler):
        """Discrete non-visibility animations use ``<p:set>`` segments, not
        TAV entries — PPT silently drops ``calcmode="discrete"`` on
        non-visibility attrNames. Verified 2026-04-16."""
        anim = make_numeric_animation(
            values=["0", "10", "20"],
            key_times=[0.0, 0.4, 1.0],
            calc_mode=CalcMode.DISCRETE,
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        sets = par.findall(f".//{{{NS_P}}}set")
        assert len(sets) == 3
        str_vals = [s.find(f".//{{{NS_P}}}strVal") for s in sets]
        vals = [v.get("val") for v in str_vals]
        assert len(vals) == 3
        assert vals[0] == "0"
        assert float(vals[1]) > 0
        assert float(vals[2]) > float(vals[1])

    def test_paced_calc_mode_overrides_explicit_key_times(
        self, handler: NumericAnimationHandler
    ):
        anim = make_numeric_animation(
            values=["0", "10", "40"],
            key_times=[0.0, 0.5, 1.0],
            calc_mode=CalcMode.PACED,
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        tavs = par.findall(f".//{{{NS_P}}}tav")
        # Distances are 10 then 30, so paced midpoint should be 25%.
        assert [tav.get("tm") for tav in tavs] == ["0", "25000", "100000"]

    def test_spline_calc_mode_densifies_generic_numeric_tavs(
        self, handler: NumericAnimationHandler
    ):
        anim = make_numeric_animation(
            target_attribute="stroke-width",
            values=["0", "100"],
            calc_mode=CalcMode.SPLINE,
            key_splines=[[0.75, 0.0, 0.25, 1.0]],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        tavs = par.findall(f".//{{{NS_P}}}tav")
        assert len(tavs) > 2
        assert tavs[0].get("tm") == "0"
        assert tavs[-1].get("tm") == "100000"

    def test_spline_width_avoids_simple_anim_scale_path(
        self, handler: NumericAnimationHandler
    ):
        anim = make_numeric_animation(
            target_attribute="width",
            values=["10", "110"],
            calc_mode=CalcMode.SPLINE,
            key_splines=[[0.75, 0.0, 0.25, 1.0]],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        assert par.find(f".//{{{NS_P}}}animScale") is None
        tavs = par.findall(f".//{{{NS_P}}}tav")
        assert len(tavs) > 2
