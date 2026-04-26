"""Shared animation predicates and grouping keys for export passes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    CalcMode,
    TransformType,
)


def _single_matching_member(
    members: list[tuple[int, AnimationDefinition]],
    predicate: Callable[[AnimationDefinition], bool],
) -> tuple[int, AnimationDefinition] | None:
    matches = [(index, animation) for index, animation in members if predicate(animation)]
    if len(matches) != 1:
        return None
    return matches[0]


def _is_simple_linear_two_value_animation(animation: AnimationDefinition) -> bool:
    if len(animation.values) != 2:
        return False
    if animation.key_times or animation.key_splines:
        return False
    calc_mode = (
        animation.calc_mode.value
        if isinstance(animation.calc_mode, CalcMode)
        else str(animation.calc_mode).lower()
    )
    return calc_mode == CalcMode.LINEAR.value


def _is_simple_line_endpoint_animation(animation: AnimationDefinition) -> bool:
    return (
        animation.animation_type == AnimationType.ANIMATE
        and animation.transform_type is None
        and animation.target_attribute in {"x1", "x2", "y1", "y2"}
        and animation.additive == "replace"
        and _is_simple_linear_two_value_animation(animation)
    )


def _is_polyline_segment_fade_animation(animation: AnimationDefinition) -> bool:
    return (
        animation.animation_type == AnimationType.ANIMATE
        and animation.transform_type is None
        and animation.target_attribute in {"opacity", "fill-opacity", "stroke-opacity"}
    )


def _is_simple_linear_numeric_animation(animation: AnimationDefinition) -> bool:
    return (
        animation.animation_type == AnimationType.ANIMATE
        and animation.transform_type is None
        and animation.additive == "replace"
        and _is_simple_linear_two_value_animation(animation)
    )


def _is_simple_motion_sampling_candidate(animation: AnimationDefinition) -> bool:
    if animation.animation_type != AnimationType.ANIMATE_MOTION:
        return False
    if animation.key_times or animation.key_splines:
        return False
    calc_mode = (
        animation.calc_mode.value
        if isinstance(animation.calc_mode, CalcMode)
        else str(animation.calc_mode).lower()
    )
    return calc_mode in {CalcMode.LINEAR.value, CalcMode.PACED.value}


def _is_simple_origin_rotate_animation(animation: AnimationDefinition) -> bool:
    from svg2ooxml.common.conversions.transforms import parse_numeric_list

    if animation.animation_type != AnimationType.ANIMATE_TRANSFORM:
        return False
    if animation.transform_type != TransformType.ROTATE:
        return False
    if not _is_simple_linear_two_value_animation(animation):
        return False
    for value in animation.values:
        if len(parse_numeric_list(value)) >= 3:
            return False
    return True


def _simple_position_axis(animation: AnimationDefinition) -> str | None:
    if animation.animation_type != AnimationType.ANIMATE:
        return None
    if animation.transform_type is not None:
        return None
    if len(animation.values) != 2:
        return None
    if animation.key_times or animation.key_splines:
        return None
    if animation.additive != "replace":
        return None

    calc_mode = (
        animation.calc_mode.value
        if isinstance(animation.calc_mode, CalcMode)
        else str(animation.calc_mode).lower()
    )
    if calc_mode != CalcMode.LINEAR.value:
        return None

    if animation.target_attribute in {"x", "cx", "ppt_x"}:
        return "x"
    if animation.target_attribute in {"y", "cy", "ppt_y"}:
        return "y"
    return None


def _parse_rotate_bounds(animation: AnimationDefinition) -> tuple[float, float]:
    from svg2ooxml.common.conversions.transforms import parse_numeric_list

    start_numbers = parse_numeric_list(animation.values[0])
    end_numbers = parse_numeric_list(animation.values[-1])
    start_angle = start_numbers[0] if start_numbers else 0.0
    end_angle = end_numbers[0] if end_numbers else start_angle
    return (start_angle, end_angle)


def _sampled_motion_group_key(
    animation: AnimationDefinition,
    alias_map: dict[str, tuple[str, ...]],
) -> tuple[Any, ...]:
    return (
        alias_map.get(animation.element_id, (animation.element_id,)),
        *_timing_group_key(animation.timing),
        animation.restart,
        animation.min_ms,
        animation.max_ms,
    )


def _timing_group_key(timing: AnimationTiming) -> tuple[Any, ...]:
    begin_triggers = tuple(
        _begin_trigger_group_key(trigger)
        for trigger in (timing.begin_triggers or [])
    )
    end_triggers = tuple(
        _begin_trigger_group_key(trigger)
        for trigger in (timing.end_triggers or [])
    )
    repeat_duration = (
        round(float(timing.repeat_duration), 6)
        if timing.repeat_duration is not None
        else None
    )
    return (
        round(float(timing.begin), 6),
        round(float(timing.duration), 6),
        str(timing.repeat_count),
        repeat_duration,
        timing.fill_mode.value,
        begin_triggers,
        end_triggers,
    )


def _begin_trigger_group_key(trigger: Any) -> tuple[Any, ...]:
    return (
        getattr(getattr(trigger, "trigger_type", None), "value", None),
        float(getattr(trigger, "delay_seconds", 0.0)),
        getattr(trigger, "target_element_id", None),
        getattr(trigger, "event_name", None),
        getattr(trigger, "repeat_iteration", None),
        getattr(trigger, "access_key", None),
        getattr(trigger, "wallclock_value", None),
    )
