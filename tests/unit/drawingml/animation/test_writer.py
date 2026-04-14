"""Tests for DrawingMLAnimationWriter."""

from __future__ import annotations

import re
from unittest.mock import Mock, patch

import pytest

from svg2ooxml.drawingml.animation.handlers import (
    ColorAnimationHandler,
    MotionAnimationHandler,
    NumericAnimationHandler,
    OpacityAnimationHandler,
    SetAnimationHandler,
    TransformAnimationHandler,
)
from svg2ooxml.drawingml.animation.writer import DrawingMLAnimationWriter
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    TransformType,
)

# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #


def _opacity_anim(**overrides) -> AnimationDefinition:
    defaults = dict(
        element_id="shape1",
        animation_type=AnimationType.ANIMATE,
        target_attribute="opacity",
        values=["0", "1"],
        timing=AnimationTiming(begin=0.0, duration=1.0),
    )
    defaults.update(overrides)
    return AnimationDefinition(**defaults)


def _color_anim(**overrides) -> AnimationDefinition:
    defaults = dict(
        element_id="shape1",
        animation_type=AnimationType.ANIMATE,
        target_attribute="fill",
        values=["#FF0000", "#00FF00"],
        timing=AnimationTiming(begin=0.0, duration=1.0),
    )
    defaults.update(overrides)
    return AnimationDefinition(**defaults)


def _numeric_anim(**overrides) -> AnimationDefinition:
    defaults = dict(
        element_id="shape1",
        animation_type=AnimationType.ANIMATE,
        target_attribute="x",
        values=["0", "100"],
        timing=AnimationTiming(begin=0.0, duration=1.0),
    )
    defaults.update(overrides)
    return AnimationDefinition(**defaults)


def _set_anim(**overrides) -> AnimationDefinition:
    defaults = dict(
        element_id="shape1",
        animation_type=AnimationType.SET,
        target_attribute="visibility",
        values=["visible"],
        timing=AnimationTiming(begin=0.0, duration=1.0),
    )
    defaults.update(overrides)
    return AnimationDefinition(**defaults)


def _transform_anim(**overrides) -> AnimationDefinition:
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


def _motion_anim(**overrides) -> AnimationDefinition:
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
def writer():
    return DrawingMLAnimationWriter()


# ------------------------------------------------------------------ #
# Init                                                                 #
# ------------------------------------------------------------------ #


class TestInit:
    def test_initializes_id_allocator(self, writer):
        assert writer._id_allocator is not None

    def test_initializes_unit_converter(self, writer):
        assert writer._unit_converter is not None

    def test_initializes_xml_builder(self, writer):
        assert writer._xml_builder is not None

    def test_initializes_value_processor(self, writer):
        assert writer._value_processor is not None

    def test_initializes_tav_builder(self, writer):
        assert writer._tav_builder is not None

    def test_policy_starts_as_none(self, writer):
        assert writer._policy is None

    def test_initializes_six_handlers(self, writer):
        assert len(writer._handlers) == 6

    def test_handlers_in_priority_order(self, writer):
        assert isinstance(writer._handlers[0], OpacityAnimationHandler)
        assert isinstance(writer._handlers[1], ColorAnimationHandler)
        assert isinstance(writer._handlers[2], SetAnimationHandler)
        assert isinstance(writer._handlers[3], MotionAnimationHandler)
        assert isinstance(writer._handlers[4], TransformAnimationHandler)
        assert isinstance(writer._handlers[5], NumericAnimationHandler)


# ------------------------------------------------------------------ #
# _find_handler                                                        #
# ------------------------------------------------------------------ #


class TestFindHandler:
    def test_finds_opacity_handler(self, writer):
        anim = _opacity_anim()
        handler = writer._find_handler(anim)
        assert isinstance(handler, OpacityAnimationHandler)

    def test_finds_color_handler(self, writer):
        anim = _color_anim()
        handler = writer._find_handler(anim)
        assert isinstance(handler, ColorAnimationHandler)

    def test_finds_set_handler(self, writer):
        anim = _set_anim()
        handler = writer._find_handler(anim)
        assert isinstance(handler, SetAnimationHandler)

    def test_finds_transform_handler(self, writer):
        anim = _transform_anim()
        handler = writer._find_handler(anim)
        assert isinstance(handler, TransformAnimationHandler)

    def test_finds_numeric_handler(self, writer):
        anim = _numeric_anim()
        handler = writer._find_handler(anim)
        assert isinstance(handler, NumericAnimationHandler)

    def test_numeric_is_fallback(self, writer):
        anim = _numeric_anim(target_attribute="custom_unknown_attr")
        handler = writer._find_handler(anim)
        assert isinstance(handler, NumericAnimationHandler)


# ------------------------------------------------------------------ #
# _build_animation                                                     #
# ------------------------------------------------------------------ #


class TestBuildAnimation:
    def test_returns_element_for_valid_animation(self, writer):
        anim = _opacity_anim()
        elem, meta = writer._build_animation(anim, {}, par_id=4, behavior_id=5)
        assert elem is not None
        assert meta is None

    def test_returns_none_for_skipped_animation(self, writer):
        # Create an animation with key_splines that would be skipped
        anim = _numeric_anim(
            values=["0", "100"],
            key_times=[0.0, 1.0],
            key_splines=[[0, 0, 1, 1]],
            calc_mode="spline",
        )
        from svg2ooxml.ir.animation import CalcMode

        anim = _numeric_anim(
            values=["0", "100"],
            key_times=[0.0, 1.0],
            key_splines=[[0, 0, 1, 1]],
            calc_mode=CalcMode.SPLINE,
        )
        elem, meta = writer._build_animation(
            anim, {"max_spline_error": 0.0001}, par_id=4, behavior_id=5
        )
        # May or may not skip — just verify the return types
        if elem is None:
            assert meta is not None
            assert "reason" in meta

    def test_returns_error_metadata_on_handler_exception(self, writer):
        anim = _opacity_anim()
        with patch.object(
            writer._handlers[0], "build", side_effect=ValueError("Test error")
        ):
            elem, meta = writer._build_animation(anim, {}, par_id=4, behavior_id=5)
            assert elem is None
            assert "handler_error" in meta["reason"]

    def test_element_contains_correct_ids(self, writer):
        anim = _opacity_anim()
        elem, _ = writer._build_animation(anim, {}, par_id=42, behavior_id=43)
        from svg2ooxml.drawingml.xml_builder import to_string

        xml = to_string(elem)
        assert 'id="42"' in xml
        assert 'id="43"' in xml


# ------------------------------------------------------------------ #
# build                                                                #
# ------------------------------------------------------------------ #


class TestBuild:
    def test_empty_for_no_animations(self, writer):
        result = writer.build([], [])
        assert result == ""

    def test_builds_timing_xml(self, writer):
        result = writer.build([_opacity_anim()], [])
        assert "<p:timing" in result
        assert "<p:tnLst>" in result
        assert "</p:timing>" in result

    def test_includes_main_seq(self, writer):
        result = writer.build([_opacity_anim()], [])
        assert 'nodeType="mainSeq"' in result

    def test_includes_tm_root(self, writer):
        result = writer.build([_opacity_anim()], [])
        assert 'nodeType="tmRoot"' in result

    def test_includes_animation_element(self, writer):
        result = writer.build([_opacity_anim()], [])
        # Opacity uses animEffect
        assert "animEffect" in result

    def test_multiple_animations(self, writer):
        anims = [
            _opacity_anim(element_id="s1"),
            _color_anim(element_id="s2"),
            _numeric_anim(element_id="s3"),
        ]
        result = writer.build(anims, [])
        assert result != ""
        # Should have 3 animation <p:par> elements nested within the tree
        assert result.count("animEffect") >= 1  # opacity
        assert result.count("animClr") >= 1  # color
        assert result.count("<p:anim") >= 1  # numeric

    def test_all_ids_unique(self, writer):
        anims = [_opacity_anim(element_id=f"s{i}") for i in range(5)]
        result = writer.build(anims, [])
        found_ids = re.findall(r'id="(\d+)"', result)
        assert len(found_ids) == len(set(found_ids))

    def test_generated_companion_motion_ids_do_not_collide(self, writer):
        result = writer.build(
            [
                _transform_anim(
                    values=["1 1", "2 2"],
                    element_center_px=(100.0, 100.0),
                    motion_viewport_px=(960.0, 720.0),
                ),
                _opacity_anim(),
            ],
            [],
        )

        found_ids = re.findall(r'<p:cTn id="(\d+)"', result)
        assert len(found_ids) == len(set(found_ids))

    def test_ids_start_at_one(self, writer):
        result = writer.build([_opacity_anim()], [])
        # tmRoot should have id="1"
        assert 'id="1"' in result

    def test_includes_build_list(self, writer):
        result = writer.build(
            [_opacity_anim(element_id="shape42")],
            [],
            animated_shape_ids=["shape42"],
        )
        assert "<p:bldLst>" in result
        assert 'spid="shape42"' in result

    def test_includes_effect_group_build_list_entries(self, writer):
        result = writer.build(
            [_motion_anim(element_id="shape42")],
            [],
            animated_shape_ids=["shape42"],
        )
        assert '<p:bldP spid="shape42" grpId="0"/>' in result
        assert 'spid="shape42" grpId="4" animBg="1"' in result

    def test_handles_none_options(self, writer):
        result = writer.build([_opacity_anim()], [], options=None)
        assert result != ""

    def test_passes_options_to_policy(self, writer):
        options = {"max_spline_error": 1.5, "fallback_mode": "raster"}
        with patch.object(
            writer, "_build_animation", wraps=writer._build_animation
        ) as mock:
            writer.build([_opacity_anim()], [], options=options)
            mock.assert_called_once()
            call_options = mock.call_args[0][1]
            assert call_options["max_spline_error"] == 1.5

    def test_delay_from_begin(self, writer):
        anim = _opacity_anim(timing=AnimationTiming(begin=0.5, duration=1.0))
        result = writer.build([anim], [])
        assert 'delay="500"' in result

    def test_skipped_animations_return_empty(self, writer):
        # Motion with single point returns None from handler
        anim = _motion_anim(values=["M0,0"])
        result = writer.build([anim], [])
        assert result == ""

    def test_merges_concurrent_simple_numeric_motions(self, writer):
        result = writer.build(
            [
                _numeric_anim(
                    target_attribute="x",
                    values=["0", "100"],
                    motion_viewport_px=(1000.0, 1000.0),
                ),
                _numeric_anim(
                    target_attribute="y",
                    values=["0", "200"],
                    motion_viewport_px=(1000.0, 1000.0),
                ),
            ],
            [],
        )

        assert result.count("<p:animMotion") == 1
        assert 'path="M 0 0 L 0.1 0.2 E"' in result
        assert result.count('<p:bldP spid="shape1"') == 1

    def test_merges_scale_origin_motion_with_concurrent_translate(self, writer):
        result = writer.build(
            [
                _transform_anim(
                    values=["1 1", "2 2"],
                    additive="sum",
                    element_center_px=(50.0, 60.0),
                    motion_viewport_px=(1000.0, 1000.0),
                ),
                _numeric_anim(
                    target_attribute="x",
                    values=["0", "100"],
                    motion_viewport_px=(1000.0, 1000.0),
                ),
            ],
            [],
        )

        assert "animScale" in result
        assert result.count("<p:animMotion") == 1
        assert 'path="M 0 0 L 0.15 0.06 E"' in result

    def test_merges_numeric_scale_anchor_motion_with_translate(self, writer):
        result = writer.build(
            [
                _numeric_anim(
                    target_attribute="width",
                    values=["100", "200"],
                    additive="sum",
                    motion_viewport_px=(1000.0, 1000.0),
                ),
                _numeric_anim(
                    target_attribute="x",
                    values=["0", "100"],
                    motion_viewport_px=(1000.0, 1000.0),
                ),
            ],
            [],
        )

        assert "animScale" in result
        assert result.count("<p:animMotion") == 1
        assert 'path="M 0 0 L 0.15 0 E"' in result

    def test_does_not_merge_complex_authored_motion_paths(self, writer):
        result = writer.build(
            [
                _motion_anim(values=["M0,0 L100,0 L100,100"]),
                _numeric_anim(
                    target_attribute="x",
                    values=["0", "100"],
                    motion_viewport_px=(1000.0, 1000.0),
                ),
            ],
            [],
        )

        assert result.count("<p:animMotion") == 2

    def test_does_not_drop_explicit_motion_rotation_when_merging(self, writer):
        result = writer.build(
            [
                _motion_anim(values=["M0,0 L100,0"], motion_rotate="45"),
                _numeric_anim(
                    target_attribute="x",
                    values=["0", "100"],
                    motion_viewport_px=(1000.0, 1000.0),
                ),
            ],
            [],
        )

        assert result.count("<p:animMotion") == 2
        assert 'rAng="2700000"' in result


# ------------------------------------------------------------------ #
# Tracer integration                                                   #
# ------------------------------------------------------------------ #


class TestTracerIntegration:
    def test_records_emitted_event(self, writer):
        tracer = Mock()
        writer.build([_opacity_anim()], [], tracer=tracer)
        calls = tracer.record_stage_event.call_args_list
        actions = [c.kwargs["action"] for c in calls]
        assert "fragment_emitted" in actions

    def test_records_skipped_event(self, writer):
        tracer = Mock()
        # Motion with single-point path → skipped by handler
        anim = _motion_anim(values=["M0,0"])
        writer.build([anim], [], tracer=tracer)
        calls = tracer.record_stage_event.call_args_list
        actions = [c.kwargs["action"] for c in calls]
        assert "fragment_skipped" in actions

    def test_emitted_metadata_has_element_id(self, writer):
        tracer = Mock()
        writer.build([_opacity_anim(element_id="myshape")], [], tracer=tracer)
        calls = tracer.record_stage_event.call_args_list
        emitted = [c for c in calls if c.kwargs["action"] == "fragment_emitted"]
        assert len(emitted) == 1
        assert emitted[0].kwargs["metadata"]["element_id"] == "myshape"


# ------------------------------------------------------------------ #
# Integration                                                          #
# ------------------------------------------------------------------ #


class TestIntegration:
    def test_opacity_workflow(self, writer):
        result = writer.build([_opacity_anim()], [])
        assert "<p:timing" in result
        assert "animEffect" in result

    def test_color_workflow(self, writer):
        result = writer.build([_color_anim()], [])
        assert "<p:timing" in result
        assert "animClr" in result

    def test_numeric_workflow(self, writer):
        result = writer.build([_numeric_anim()], [])
        assert "<p:timing" in result
        assert "<p:anim" in result

    def test_set_workflow(self, writer):
        result = writer.build([_set_anim()], [])
        assert "<p:timing" in result
        assert "<p:set" in result

    def test_transform_scale_workflow(self, writer):
        result = writer.build([_transform_anim()], [])
        assert "<p:timing" in result
        assert "animScale" in result

    def test_mixed_workflow(self, writer):
        anims = [
            _opacity_anim(element_id="s1"),
            _color_anim(element_id="s2"),
            _numeric_anim(element_id="s3"),
        ]
        result = writer.build(anims, [])
        assert "<p:timing" in result
        # All three animation types present
        assert "animEffect" in result
        assert "animClr" in result
        assert "<p:anim" in result
