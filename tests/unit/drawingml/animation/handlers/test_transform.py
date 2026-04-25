"""Tests for TransformAnimationHandler."""

from __future__ import annotations

import pytest
from lxml import etree

from svg2ooxml.common.geometry.matrix import Matrix2D
from svg2ooxml.common.units import UnitConverter
from svg2ooxml.drawingml.animation.handlers.transform import TransformAnimationHandler
from svg2ooxml.drawingml.animation.tav_builder import TAVBuilder
from svg2ooxml.drawingml.animation.value_processors import ValueProcessor
from svg2ooxml.drawingml.animation.xml_builders import AnimationXMLBuilder
from svg2ooxml.drawingml.xml_builder import NS_P
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    CalcMode,
    TransformType,
)


def make_transform_animation(**overrides) -> AnimationDefinition:
    """Build a real AnimationDefinition for transform animations."""
    defaults = dict(
        element_id="shape1",
        animation_type=AnimationType.ANIMATE_TRANSFORM,
        target_attribute="transform",
        values=["1", "2"],
        timing=AnimationTiming(begin=0.0, duration=1.0),
        transform_type=TransformType.SCALE,
    )
    defaults.update(overrides)
    return AnimationDefinition(**defaults)


@pytest.fixture
def handler() -> TransformAnimationHandler:
    xml = AnimationXMLBuilder()
    vp = ValueProcessor()
    tav = TAVBuilder(xml)
    uc = UnitConverter()
    return TransformAnimationHandler(xml, vp, tav, uc)


# ------------------------------------------------------------------ #
# can_handle                                                          #
# ------------------------------------------------------------------ #


class TestCanHandle:
    def test_handles_scale(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(transform_type=TransformType.SCALE)
        assert handler.can_handle(anim) is True

    def test_handles_rotate(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(transform_type=TransformType.ROTATE)
        assert handler.can_handle(anim) is True

    def test_handles_translate(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(transform_type=TransformType.TRANSLATE)
        assert handler.can_handle(anim) is True

    def test_handles_matrix(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(transform_type=TransformType.MATRIX)
        assert handler.can_handle(anim) is True

    def test_rejects_none_transform(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(transform_type=None)
        assert handler.can_handle(anim) is False

    def test_rejects_skewx(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(transform_type=TransformType.SKEWX)
        assert handler.can_handle(anim) is False

    def test_rejects_skewy(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(transform_type=TransformType.SKEWY)
        assert handler.can_handle(anim) is False


# ------------------------------------------------------------------ #
# build — scale                                                       #
# ------------------------------------------------------------------ #


class TestBuildScale:
    def test_returns_par_element(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.SCALE, values=["1", "2"]
        )
        result = handler.build(anim, par_id=4, behavior_id=5)
        assert isinstance(result, etree._Element)
        assert result.tag == f"{{{NS_P}}}par"

    def test_ctn_has_correct_id(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.SCALE, values=["1", "2"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("id") == "4"

    def test_anim_scale_present(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.SCALE, values=["1", "2"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_scale = par.find(f".//{{{NS_P}}}animScale")
        assert anim_scale is not None

    def test_scale_does_not_target_rotation(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.SCALE, values=["1", "2"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_scale = par.find(f".//{{{NS_P}}}animScale")
        attr_names = anim_scale.findall(f".//{{{NS_P}}}attrName")
        assert [node.text for node in attr_names] == []

    def test_behavior_id(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.SCALE, values=["1", "2"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        bhvr_ctn = par.find(f".//{{{NS_P}}}cBhvr/{{{NS_P}}}cTn")
        assert bhvr_ctn.get("id") == "5"

    def test_target_shape(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.SCALE,
            values=["1", "2"],
            element_id="shape42",
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        sp_tgt = par.find(f".//{{{NS_P}}}spTgt")
        assert sp_tgt.get("spid") == "shape42"

    def test_from_scale_values(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.SCALE, values=["1", "2"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        from_elem = par.find(f".//{{{NS_P}}}from")
        assert from_elem is not None
        assert from_elem.get("x") == "100000"
        assert from_elem.get("y") == "100000"

    def test_to_scale_values(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.SCALE, values=["1", "2"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        to_elem = par.find(f".//{{{NS_P}}}to")
        assert to_elem is not None
        assert to_elem.get("x") == "200000"
        assert to_elem.get("y") == "200000"

    def test_asymmetric_scale(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.SCALE, values=["1 2", "3 4"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        from_elem = par.find(f".//{{{NS_P}}}from")
        assert from_elem.get("x") == "100000"
        assert from_elem.get("y") == "200000"
        to_elem = par.find(f".//{{{NS_P}}}to")
        assert to_elem.get("x") == "300000"
        assert to_elem.get("y") == "400000"

    def test_preset_attrs_for_scale(self, handler: TransformAnimationHandler):
        """Scale transforms use Grow/Shrink emphasis preset."""
        anim = make_transform_animation(
            transform_type=TransformType.SCALE, values=["1", "2"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("presetClass") == "emph"
        assert ctn.get("presetID") == "6"

    def test_single_scale_value(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.SCALE, values=["2"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        assert par is not None
        from_elem = par.find(f".//{{{NS_P}}}from")
        to_elem = par.find(f".//{{{NS_P}}}to")
        # Single value: from and to are the same
        assert from_elem.get("x") == to_elem.get("x")

    def test_scale_with_element_center_adds_origin_compensation_motion(
        self, handler: TransformAnimationHandler
    ):
        anim = make_transform_animation(
            transform_type=TransformType.SCALE,
            values=["1", "2"],
            element_center_px=(100.0, 60.0),
            motion_viewport_px=(480.0, 360.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        motions = par.findall(f".//{{{NS_P}}}animMotion")
        assert len(motions) == 1
        assert motions[0].get("path") == "M 0 0 L 0.208333 0.166667 E"

    def test_scale_from_zero_to_one_does_not_overshoot_origin_compensation(
        self, handler: TransformAnimationHandler
    ):
        anim = make_transform_animation(
            transform_type=TransformType.SCALE,
            values=["0", "1"],
            element_center_px=(100.0, 60.0),
            motion_viewport_px=(480.0, 360.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        motions = par.findall(f".//{{{NS_P}}}animMotion")
        assert len(motions) == 0

    def test_scale_without_element_center_skips_origin_compensation_motion(
        self, handler: TransformAnimationHandler
    ):
        anim = make_transform_animation(
            transform_type=TransformType.SCALE,
            values=["1", "2"],
            motion_viewport_px=(480.0, 360.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        motions = par.findall(f".//{{{NS_P}}}animMotion")
        assert len(motions) == 0

    def test_delay_from_begin(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.SCALE,
            values=["1", "2"],
            timing=AnimationTiming(begin=0.5, duration=1.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        cond = par.find(f".//{{{NS_P}}}cTn/{{{NS_P}}}stCondLst/{{{NS_P}}}cond")
        assert cond.get("delay") == "500"

    def test_duration(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.SCALE,
            values=["1", "2"],
            timing=AnimationTiming(begin=0.0, duration=2.5),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("dur") == "2500"


# ------------------------------------------------------------------ #
# build — rotate                                                      #
# ------------------------------------------------------------------ #


class TestBuildRotate:
    def test_returns_par_element(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE, values=["0", "360"]
        )
        result = handler.build(anim, par_id=4, behavior_id=5)
        assert isinstance(result, etree._Element)
        assert result.tag == f"{{{NS_P}}}par"

    def test_anim_rot_present(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE, values=["0", "360"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_rot = par.find(f".//{{{NS_P}}}animRot")
        assert anim_rot is not None

    def test_rotation_delta(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE, values=["0", "360"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_rot = par.find(f".//{{{NS_P}}}animRot")
        # 360 * 60000 = 21600000
        assert anim_rot.get("by") == "21600000"

    def test_rotation_partial_delta(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE, values=["45", "90"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_rot = par.find(f".//{{{NS_P}}}animRot")
        # (90 - 45) * 60000 = 2700000
        assert anim_rot.get("by") == "2700000"

    def test_behavior_id(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE, values=["0", "360"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        bhvr_ctn = par.find(f".//{{{NS_P}}}cBhvr/{{{NS_P}}}cTn")
        assert bhvr_ctn.get("id") == "5"

    def test_rotate_targets_r_attribute(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE, values=["0", "360"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        attr_names = [node.text for node in par.findall(f".//{{{NS_P}}}attrName")]
        assert "r" in attr_names

    def test_single_rotate_value(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE, values=["45"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        assert par is not None
        anim_rot = par.find(f".//{{{NS_P}}}animRot")
        # Delta = 45 - 45 = 0
        assert anim_rot.get("by") == "0"


class TestMultiKeyframeRotate:
    """Multi-keyframe rotate splits into sequential segments."""

    def test_three_values_produces_two_anim_rot(
        self, handler: TransformAnimationHandler
    ):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE, values=["0", "360", "0"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        rots = par.findall(f".//{{{NS_P}}}animRot")
        assert len(rots) == 2

    def test_three_values_deltas(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE, values=["0", "360", "0"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        rots = par.findall(f".//{{{NS_P}}}animRot")
        # First segment: 0→360 = +21600000, second: 360→0 = -21600000
        assert rots[0].get("by") == "21600000"
        assert rots[1].get("by") == "-21600000"

    def test_four_values_produces_three_segments(
        self, handler: TransformAnimationHandler
    ):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE, values=["0", "90", "180", "0"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        rots = par.findall(f".//{{{NS_P}}}animRot")
        assert len(rots) == 3
        assert rots[0].get("by") == "5400000"  # 90°
        assert rots[1].get("by") == "5400000"  # 90°
        assert rots[2].get("by") == "-10800000"  # -180°

    def test_key_times_affect_segment_durations(
        self, handler: TransformAnimationHandler
    ):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE,
            values=["0", "360", "0"],
            key_times=[0.0, 0.75, 1.0],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        # Duration 1000ms total. Segments: 75% = 750ms, 25% = 250ms
        seg_pars = par.findall(f".//{{{NS_P}}}cTn/{{{NS_P}}}childTnLst/{{{NS_P}}}par")
        seg0_dur = seg_pars[0].find(f"{{{NS_P}}}cTn").get("dur")
        seg1_dur = seg_pars[1].find(f"{{{NS_P}}}cTn").get("dur")
        assert seg0_dur == "750"
        assert seg1_dur == "250"

    def test_returns_par_element(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE, values=["0", "180", "0"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        assert par.tag == f"{{{NS_P}}}par"

    def test_outer_par_has_preset(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE, values=["0", "360", "0"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("presetID") == "8"
        assert ctn.get("presetClass") == "emph"

    def test_simple_transform_uses_nonzero_effect_group(
        self, handler: TransformAnimationHandler
    ):
        anim = make_transform_animation(
            transform_type=TransformType.SCALE, values=["1", "2"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("grpId") == "4"


class TestRotateWithOrbit:
    """Rotation with cx/cy center generates companion orbital motion."""

    def test_orbit_produces_anim_motion(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE,
            values=["0 40 40", "360 40 40"],
            element_center_px=(80.0, 80.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        motions = par.findall(f".//{{{NS_P}}}animMotion")
        assert len(motions) == 1

    def test_orbit_motion_has_path(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE,
            values=["0 40 40", "90 40 40"],
            element_center_px=(80.0, 80.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        motion = par.find(f".//{{{NS_P}}}animMotion")
        path = motion.get("path")
        assert path.startswith("M 0 0")
        assert "L " in path

    def test_no_orbit_when_center_matches(self, handler: TransformAnimationHandler):
        """No motion path when shape center ≈ rotation center."""
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE,
            values=["0 80 80", "360 80 80"],
            element_center_px=(80.0, 80.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        motions = par.findall(f".//{{{NS_P}}}animMotion")
        assert len(motions) == 0

    def test_no_orbit_without_center_info(self, handler: TransformAnimationHandler):
        """No motion path when element_center_px is not available."""
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE,
            values=["0 40 40", "360 40 40"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        motions = par.findall(f".//{{{NS_P}}}animMotion")
        assert len(motions) == 0

    def test_no_orbit_without_cxcy(self, handler: TransformAnimationHandler):
        """No motion path when values have no cx/cy."""
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE,
            values=["0", "360"],
            element_center_px=(80.0, 80.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        motions = par.findall(f".//{{{NS_P}}}animMotion")
        assert len(motions) == 0

    def test_multi_keyframe_with_orbit(self, handler: TransformAnimationHandler):
        """Multi-keyframe rotate with cx/cy adds orbit as extra child."""
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE,
            values=["0 40 40", "360 40 40", "0 40 40"],
            element_center_px=(80.0, 80.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        rots = par.findall(f".//{{{NS_P}}}animRot")
        motions = par.findall(f".//{{{NS_P}}}animMotion")
        assert len(rots) == 2  # multi-keyframe split
        assert len(motions) == 1  # orbital companion

    def test_symmetric_multi_keyframe_orbit_path_is_not_collapsed(
        self, handler: TransformAnimationHandler
    ):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE,
            values=["0 40 40", "-45 40 40", "0 40 40"],
            element_center_px=(80.0, 80.0),
            motion_viewport_px=(160.0, 100.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        motion = par.find(f".//{{{NS_P}}}animMotion")
        assert motion is not None
        path = motion.get("path")
        assert path is not None
        coords = [
            float(token)
            for segment in path.split("L ")[1:]
            for token in segment.strip().rstrip(" E").split()
        ]
        assert any(abs(value) > 1e-6 for value in coords)
        assert max(abs(value) for value in coords) > 0.2

    def test_multi_keyframe_rotate_uses_nonzero_effect_group(
        self, handler: TransformAnimationHandler
    ):
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE,
            values=["0", "360", "0"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn is not None
        assert ctn.get("grpId") == "4"

    def test_orbit_path_has_nonzero_values(self, handler: TransformAnimationHandler):
        """Orbit path coordinates should be non-trivial for offset center."""
        anim = make_transform_animation(
            transform_type=TransformType.ROTATE,
            values=["0 0 0", "360 0 0"],
            element_center_px=(100.0, 100.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        motion = par.find(f".//{{{NS_P}}}animMotion")
        path = motion.get("path")
        # Should have non-zero coordinates (shape orbits around origin)
        parts = path.split("L ")[1:]  # skip M 0 0
        coords = [p.strip().rstrip(" E").split() for p in parts]
        has_nonzero = any(
            abs(float(c[0])) > 1e-6 or abs(float(c[1])) > 1e-6
            for c in coords
            if len(c) == 2
        )
        assert has_nonzero


# ------------------------------------------------------------------ #
# build — translate                                                   #
# ------------------------------------------------------------------ #


class TestBuildTranslate:
    def test_returns_par_element(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE, values=["0 0", "10 20"]
        )
        result = handler.build(anim, par_id=4, behavior_id=5)
        assert isinstance(result, etree._Element)
        assert result.tag == f"{{{NS_P}}}par"

    def test_anim_motion_present(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE, values=["0 0", "10 20"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        assert anim_motion is not None

    def test_two_value_translate_uses_relative_path(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE, values=["0 0", "10 20"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        by_elem = par.find(f".//{{{NS_P}}}by")
        assert by_elem is None
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        assert anim_motion is not None
        assert anim_motion.get("path") is not None
        assert anim_motion.get("pathEditMode") == "relative"

    def test_two_value_translate_uses_scene_viewport(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE,
            values=["0 0", "10 20"],
            motion_viewport_px=(480.0, 360.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        assert anim_motion is not None
        assert anim_motion.get("path") == "M 0 0 L 0.0208333 0.0555556 E"

    def test_two_value_translate_projects_motion_space_matrix(
        self, handler: TransformAnimationHandler
    ):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE,
            values=["0 0", "10 20"],
            motion_viewport_px=(480.0, 360.0),
            motion_space_matrix=(2.0, 0.0, 0.0, 3.0, 50.0, 90.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        assert anim_motion is not None
        assert anim_motion.get("path") == "M 0 0 L 0.0416667 0.166667 E"

    def test_preset_class_is_path(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE, values=["0 0", "10 20"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("presetClass") == "path"

    def test_returns_none_for_single_value(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE, values=["10 20"]
        )
        result = handler.build(anim, par_id=4, behavior_id=5)
        assert result is None

    def test_behavior_id(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE, values=["0 0", "10 20"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        bhvr_ctn = par.find(f".//{{{NS_P}}}cBhvr/{{{NS_P}}}cTn")
        assert bhvr_ctn.get("id") == "5"


# ------------------------------------------------------------------ #
# build — translate multi-keyframe                                     #
# ------------------------------------------------------------------ #


class TestBuildTranslateMultiKeyframe:
    def test_three_values_uses_path(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE,
            values=["0 0", "50 0", "50 50"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        assert anim_motion is not None
        assert anim_motion.get("path") is not None

    def test_path_starts_with_M(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE,
            values=["0 0", "50 0", "50 50"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        path = anim_motion.get("path")
        assert path.startswith("M ")

    def test_path_ends_with_E(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE,
            values=["0 0", "50 0", "50 50"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        path = anim_motion.get("path")
        assert path.endswith(" E")

    def test_path_has_correct_segment_count(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE,
            values=["0 0", "50 0", "50 50", "100 100"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        path = anim_motion.get("path")
        # 1 M + 3 L segments
        assert path.count("M ") == 1
        assert path.count("L ") == 3

    def test_path_first_point_is_zero(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE,
            values=["10 20", "60 20", "60 70"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        path = anim_motion.get("path")
        # First point should be M 0 0 (relative to start)
        assert path.startswith("M 0 0 ")

    def test_has_origin_and_edit_mode(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE,
            values=["0 0", "50 0", "50 50"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        assert anim_motion.get("origin") == "layout"
        assert anim_motion.get("pathEditMode") == "relative"

    def test_has_attr_name_list(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE,
            values=["0 0", "50 0", "50 50"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        attr_names = par.findall(f".//{{{NS_P}}}attrName")
        texts = [n.text for n in attr_names]
        assert "ppt_x" in texts
        assert "ppt_y" in texts

    def test_pts_types_matches_point_count(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE,
            values=["0 0", "50 0", "50 50"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        assert anim_motion.get("ptsTypes") == "AAA"

    def test_two_values_emit_path_not_by(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE, values=["0 0", "10 20"]
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        assert anim_motion is not None
        assert anim_motion.get("path") is not None
        assert par.find(f".//{{{NS_P}}}by") is None

    def test_multi_keyframe_translate_uses_scene_viewport(
        self, handler: TransformAnimationHandler
    ):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE,
            values=["0 0", "50 0", "50 50"],
            motion_viewport_px=(480.0, 360.0),
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        assert anim_motion is not None
        assert anim_motion.get("path") == "M 0 0 L 0.104167 0 L 0.104167 0.138889 E"

    def test_discrete_calc_mode_expands_step_path(
        self, handler: TransformAnimationHandler
    ):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE,
            values=["0 0", "50 0", "50 50"],
            key_times=[0.0, 0.4, 1.0],
            calc_mode=CalcMode.DISCRETE,
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        path = anim_motion.get("path")
        # Discrete mode duplicates boundary points to hold then jump.
        assert path.count("L ") > 2
        assert len(anim_motion.get("ptsTypes")) > 3

    def test_paced_calc_mode_respects_distance_weighting(
        self, handler: TransformAnimationHandler
    ):
        anim = make_transform_animation(
            transform_type=TransformType.TRANSLATE,
            values=["0 0", "10 0", "40 0"],
            key_times=[0.0, 0.9, 1.0],  # should be overridden by paced timing
            calc_mode=CalcMode.PACED,
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        # Paced mode should expand intermediate samples, not keep 3-point path.
        assert len(anim_motion.get("ptsTypes")) > 3


# ------------------------------------------------------------------ #
# build — matrix                                                      #
# ------------------------------------------------------------------ #


class TestBuildMatrix:
    def test_matrix_translate_returns_anim_motion(
        self, handler: TransformAnimationHandler
    ):
        anim = make_transform_animation(
            transform_type=TransformType.MATRIX,
            values=["1 0 0 1 0 0", "1 0 0 1 15 5"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        assert par is not None
        anim_motion = par.find(f".//{{{NS_P}}}animMotion")
        assert anim_motion is not None

    def test_matrix_translate_preset_class(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.MATRIX,
            values=["1 0 0 1 0 0", "1 0 0 1 15 5"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("presetClass") == "path"

    def test_matrix_scale_returns_anim_scale(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.MATRIX,
            values=["2 0 0 2 0 0", "3 0 0 3 0 0"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        assert par is not None
        anim_scale = par.find(f".//{{{NS_P}}}animScale")
        assert anim_scale is not None

    def test_matrix_scale_from_to(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.MATRIX,
            values=["2 0 0 2 0 0", "3 0 0 3 0 0"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        from_elem = par.find(f".//{{{NS_P}}}from")
        assert from_elem.get("x") == "200000"
        assert from_elem.get("y") == "200000"
        to_elem = par.find(f".//{{{NS_P}}}to")
        assert to_elem.get("x") == "300000"
        assert to_elem.get("y") == "300000"

    def test_matrix_rotate_returns_anim_rot(self, handler: TransformAnimationHandler):
        # rotate(30) matrix ≈ cos30, sin30, -sin30, cos30, 0, 0
        rotation_matrix = "0.8660254 0.5 -0.5 0.8660254 0 0"
        anim = make_transform_animation(
            transform_type=TransformType.MATRIX,
            values=[rotation_matrix, "1 0 0 1 0 0"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        assert par is not None
        anim_rot = par.find(f".//{{{NS_P}}}animRot")
        assert anim_rot is not None

    def test_matrix_composite_decomposes(self, handler: TransformAnimationHandler):
        """Matrix with scale+translate decomposes; translate wins."""
        anim = make_transform_animation(
            transform_type=TransformType.MATRIX,
            values=["1 0 0 1 0 0", "2 0 0 2 5 5"],
        )
        par = handler.build(anim, par_id=4, behavior_id=5)
        assert par is not None
        ctn = par.find(f"{{{NS_P}}}cTn")
        # Translate is dominant → path preset class
        assert ctn.get("presetClass") == "path"

    def test_matrix_all_identity_returns_none(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(
            transform_type=TransformType.MATRIX,
            values=["1 0 0 1 0 0", "1 0 0 1 0 0"],
        )
        result = handler.build(anim, par_id=4, behavior_id=5)
        assert result is None


# ------------------------------------------------------------------ #
# build — returns None for bad inputs                                 #
# ------------------------------------------------------------------ #


class TestBuildReturnsNone:
    def test_none_transform_type(self, handler: TransformAnimationHandler):
        anim = make_transform_animation(transform_type=None)
        result = handler.build(anim, par_id=4, behavior_id=5)
        assert result is None


# ------------------------------------------------------------------ #
# _build_scale_tav_list                                               #
# ------------------------------------------------------------------ #


# ------------------------------------------------------------------ #
# _classify_matrix                                                    #
# ------------------------------------------------------------------ #


class TestClassifyMatrix:
    def test_identity(self, handler: TransformAnimationHandler):
        m = Matrix2D(1, 0, 0, 1, 0, 0)
        assert handler._classify_matrix(m) == ("identity", None)

    def test_translate(self, handler: TransformAnimationHandler):
        m = Matrix2D(1, 0, 0, 1, 10, 20)
        mtype, payload = handler._classify_matrix(m)
        assert mtype == "translate"
        assert payload == (10.0, 20.0)

    def test_scale(self, handler: TransformAnimationHandler):
        m = Matrix2D(2, 0, 0, 3, 0, 0)
        mtype, payload = handler._classify_matrix(m)
        assert mtype == "scale"
        assert payload == (2.0, 3.0)

    def test_rotation(self, handler: TransformAnimationHandler):
        import math

        angle = 30.0
        c = math.cos(math.radians(angle))
        s = math.sin(math.radians(angle))
        m = Matrix2D(c, s, -s, c, 0, 0)
        mtype, payload = handler._classify_matrix(m)
        assert mtype == "rotate"
        assert abs(payload - 30.0) < 0.01

    def test_composite_decomposes_to_translate(
        self, handler: TransformAnimationHandler
    ):
        """Scale+translate composite decomposes; translate wins by priority."""
        m = Matrix2D(2, 0, 0, 2, 5, 5)
        mtype, payload = handler._classify_matrix(m)
        assert mtype == "translate"
        assert payload == (5.0, 5.0)

    def test_nan_returns_none(self, handler: TransformAnimationHandler):
        m = Matrix2D(float("nan"), 0, 0, 1, 0, 0)
        mtype, payload = handler._classify_matrix(m)
        assert mtype is None

    def test_inf_returns_none(self, handler: TransformAnimationHandler):
        m = Matrix2D(float("inf"), 0, 0, 1, 0, 0)
        mtype, payload = handler._classify_matrix(m)
        assert mtype is None


# ------------------------------------------------------------------ #
# _decompose_matrix                                                   #
# ------------------------------------------------------------------ #


class TestDecomposeMatrix:
    def test_translate_plus_scale(self, handler: TransformAnimationHandler):
        """Matrix with translate + scale: should pick translate (dominant)."""
        # [2 0 0 2 10 20] = scale(2,2) + translate(10,20)
        m = Matrix2D(2, 0, 0, 2, 10, 20)
        result = handler._decompose_matrix(m)
        assert result is not None
        mtype, payload = result
        assert mtype == "translate"
        assert payload == (10.0, 20.0)

    def test_rotate_plus_translate(self, handler: TransformAnimationHandler):
        """Matrix with rotation + translation: should pick translate."""
        import math

        angle = 30.0
        c = math.cos(math.radians(angle))
        s = math.sin(math.radians(angle))
        # [cos sin -sin cos tx ty]
        m = Matrix2D(c, s, -s, c, 5, 10)
        result = handler._decompose_matrix(m)
        assert result is not None
        mtype, payload = result
        assert mtype == "translate"
        assert payload == (5.0, 10.0)

    def test_rotate_plus_scale(self, handler: TransformAnimationHandler):
        """Matrix with rotation + scale: should pick rotate."""
        import math

        angle = 45.0
        c = math.cos(math.radians(angle))
        s = math.sin(math.radians(angle))
        sx, sy = 2.0, 2.0
        # [sx*cos sx*sin -sy*sin sy*cos 0 0]
        m = Matrix2D(sx * c, sx * s, -sy * s, sy * c, 0, 0)
        result = handler._decompose_matrix(m)
        assert result is not None
        mtype, _ = result
        assert mtype == "rotate"

    def test_full_composite(self, handler: TransformAnimationHandler):
        """Matrix with translate + rotate + scale: should pick translate."""
        import math

        angle = 30.0
        c = math.cos(math.radians(angle))
        s = math.sin(math.radians(angle))
        sx, sy = 1.5, 1.5
        m = Matrix2D(sx * c, sx * s, -sy * s, sy * c, 10, 20)
        result = handler._decompose_matrix(m)
        assert result is not None
        mtype, payload = result
        assert mtype == "translate"
        assert payload == (10.0, 20.0)

    def test_skew_returns_none(self, handler: TransformAnimationHandler):
        """Matrix with skew component cannot be decomposed."""
        # Skew X by 30 degrees: [1, 0, tan(30), 1, 0, 0]
        import math

        m = Matrix2D(1, 0, math.tan(math.radians(30)), 1, 0, 0)
        result = handler._decompose_matrix(m)
        assert result is None

    def test_degenerate_returns_none(self, handler: TransformAnimationHandler):
        """Zero-scale matrix returns None."""
        m = Matrix2D(0, 0, 0, 0, 10, 20)
        result = handler._decompose_matrix(m)
        assert result is None

    def test_reflection(self, handler: TransformAnimationHandler):
        """Flip X decomposes as rotate (180°) + scale(1, -1); rotate wins."""
        m = Matrix2D(-1, 0, 0, 1, 0, 0)
        result = handler._decompose_matrix(m)
        assert result is not None
        mtype, payload = result
        # atan2(0, -1) = 180° — rotation is the dominant component
        assert mtype == "rotate"
        assert abs(payload - 180.0) < 0.01


class TestClassifyMatrixComposite:
    """Tests for _classify_matrix handling composite matrices via decomposition."""

    def test_translate_plus_scale_classified(self, handler: TransformAnimationHandler):
        m = Matrix2D(2, 0, 0, 2, 10, 20)
        mtype, payload = handler._classify_matrix(m)
        assert mtype == "translate"

    def test_classify_falls_through_to_decompose(
        self, handler: TransformAnimationHandler
    ):
        """A matrix that fails simple classification is decomposed."""
        import math

        angle = 30.0
        c = math.cos(math.radians(angle))
        s = math.sin(math.radians(angle))
        m = Matrix2D(c, s, -s, c, 5, 10)
        mtype, _ = handler._classify_matrix(m)
        # Should not return None anymore — decomposition handles it
        assert mtype is not None

    def test_skew_still_returns_none(self, handler: TransformAnimationHandler):
        """Skew matrices still return None even with decomposition."""
        import math

        m = Matrix2D(1, 0, math.tan(math.radians(30)), 1, 0, 0)
        mtype, _ = handler._classify_matrix(m)
        assert mtype is None


# ------------------------------------------------------------------ #
# _identity_payload                                                   #
# ------------------------------------------------------------------ #


class TestIdentityPayload:
    def test_translate(self, handler: TransformAnimationHandler):
        assert handler._identity_payload("translate") == (0.0, 0.0)

    def test_scale(self, handler: TransformAnimationHandler):
        assert handler._identity_payload("scale") == (1.0, 1.0)

    def test_rotate(self, handler: TransformAnimationHandler):
        assert handler._identity_payload("rotate") == 0.0

    def test_unknown(self, handler: TransformAnimationHandler):
        assert handler._identity_payload("other") == (0.0, 0.0)
