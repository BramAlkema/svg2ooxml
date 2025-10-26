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
    TransformType,
    format_transform_string,
)


def test_animation_timing_end_time_indefinite() -> None:
    timing = AnimationTiming(begin=1.0, duration=2.0, repeat_count="indefinite")
    assert math.isinf(timing.get_end_time())
    assert timing.is_active_at_time(5.0)


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
