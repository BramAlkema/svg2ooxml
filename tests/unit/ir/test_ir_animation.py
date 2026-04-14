from __future__ import annotations

import math

import pytest

from svg2ooxml.ir.animation import (
    AnimationComplexity,
    AnimationDefinition,
    AnimationKeyframe,
    AnimationSummary,
    AnimationTiming,
    AnimationType,
    BeginTrigger,
    BeginTriggerType,
    TransformType,
    format_transform_string,
)


def test_animation_timing_end_time_indefinite() -> None:
    timing = AnimationTiming(begin=1.0, duration=2.0, repeat_count="indefinite")
    assert math.isinf(timing.get_end_time())
    assert timing.is_active_at_time(5.0)


def test_animation_timing_repeat_duration_bounds_indefinite_repeat() -> None:
    timing = AnimationTiming(
        begin=1.0,
        duration=2.0,
        repeat_count="indefinite",
        repeat_duration=5.5,
    )
    assert timing.get_end_time() == pytest.approx(6.5)
    assert timing.is_active_at_time(6.0)
    assert not timing.is_active_at_time(7.0)


def test_animation_timing_can_store_begin_triggers() -> None:
    timing = AnimationTiming(
        begin=0.0,
        begin_triggers=[
            BeginTrigger(
                trigger_type=BeginTriggerType.ELEMENT_END,
                target_element_id="shape1",
                delay_seconds=0.5,
            )
        ],
    )
    assert timing.begin == 0.0
    assert timing.begin_triggers is not None
    assert timing.begin_triggers[0].trigger_type is BeginTriggerType.ELEMENT_END
    assert timing.begin_triggers[0].target_element_id == "shape1"
    assert timing.begin_triggers[0].delay_seconds == pytest.approx(0.5)


def test_animation_timing_can_store_end_triggers() -> None:
    timing = AnimationTiming(
        end_triggers=[
            BeginTrigger(
                trigger_type=BeginTriggerType.CLICK,
                target_element_id="stopButton",
                delay_seconds=0.25,
            )
        ],
    )
    assert timing.end_triggers is not None
    assert timing.end_triggers[0].trigger_type is BeginTriggerType.CLICK
    assert timing.end_triggers[0].target_element_id == "stopButton"
    assert timing.end_triggers[0].delay_seconds == pytest.approx(0.25)


def test_begin_trigger_can_store_non_clock_event_fields() -> None:
    trigger = BeginTrigger(
        trigger_type=BeginTriggerType.ELEMENT_REPEAT,
        target_element_id="loop",
        event_name="repeat",
        repeat_iteration="1/4",
    )

    assert trigger.target_element_id == "loop"
    assert trigger.event_name == "repeat"
    assert trigger.repeat_iteration == "1/4"


def test_animation_definition_keyframe_validation() -> None:
    timing = AnimationTiming()
    with pytest.raises(ValueError):
        AnimationDefinition(
            element_id="shape",
            animation_type=AnimationType.ANIMATE,
            target_attribute="opacity",
            values=["0", "1"],
            timing=timing,
            key_times=[0.0],
        )


def test_animation_definition_allows_motion_path_key_times() -> None:
    definition = AnimationDefinition(
        element_id="shape",
        animation_type=AnimationType.ANIMATE_MOTION,
        target_attribute="position",
        values=["M0,0 L100,0"],
        timing=AnimationTiming(),
        key_times=[0.0, 0.5, 1.0],
    )
    assert definition.key_times == [0.0, 0.5, 1.0]


def test_animation_definition_carries_smil_plumbing_fields() -> None:
    definition = AnimationDefinition(
        element_id="shape",
        animation_type=AnimationType.ANIMATE_MOTION,
        target_attribute="position",
        values=["M0,0 L100,0"],
        timing=AnimationTiming(repeat_duration=3.0),
        attribute_type="XML",
        from_value="0 0",
        to_value="100 0",
        by_value="10 0",
        key_points=[0.0, 0.25, 1.0],
        raw_attributes={"keyPoints": "0;.25;1"},
    )
    assert definition.attribute_type == "XML"
    assert definition.from_value == "0 0"
    assert definition.to_value == "100 0"
    assert definition.by_value == "10 0"
    assert definition.key_points == [0.0, 0.25, 1.0]
    assert definition.repeat_duration_ms == 3000
    assert definition.raw_attributes["keyPoints"] == "0;.25;1"
    assert definition.end_triggers is None


def test_animation_definition_generates_even_keyframes() -> None:
    definition = AnimationDefinition(
        element_id="shape",
        animation_type=AnimationType.ANIMATE,
        target_attribute="opacity",
        values=["0", "0.5", "1"],
        timing=AnimationTiming(duration=2.0),
    )

    keyframes = definition.get_keyframes()
    assert [kf.time for kf in keyframes] == [0.0, 0.5, 1.0]
    assert all(isinstance(kf, AnimationKeyframe) for kf in keyframes)


def test_animation_definition_interpolates_numeric_values() -> None:
    definition = AnimationDefinition(
        element_id="shape",
        animation_type=AnimationType.ANIMATE,
        target_attribute="opacity",
        values=["0", "1"],
        timing=AnimationTiming(duration=4.0, begin=2.0),
    )

    assert definition.get_value_at_time(1.0) == "0"
    assert definition.get_value_at_time(2.0) == pytest.approx(0.0)
    assert definition.get_value_at_time(4.0) == pytest.approx(0.5)
    assert definition.get_value_at_time(6.0) == "1"


def test_format_transform_string_handles_rotate() -> None:
    result = format_transform_string(TransformType.ROTATE, [90.0, 10.0, 10.0])
    assert result == "rotate(90.0, 10.0, 10.0)"


def test_animation_summary_complexity_scoring() -> None:
    summary = AnimationSummary(
        total_animations=6,
        duration=12.0,
        element_count=9,
        has_transforms=True,
        has_motion_paths=True,
        has_easing=True,
    )
    summary.calculate_complexity()
    assert summary.complexity is AnimationComplexity.VERY_COMPLEX


def test_animation_scene_merge_merges_states() -> None:
    from svg2ooxml.ir.animation import AnimationScene

    left = AnimationScene(time=0.0, element_states={"shape": {"opacity": "0"}})
    right = AnimationScene(time=0.5, element_states={"shape": {"opacity": "1"}, "other": {"fill": "#fff"}})

    left.merge_scene(right)

    assert left.get_element_property("shape", "opacity") == "1"
    assert left.get_element_property("other", "fill") == "#fff"
