"""Deterministic repeat-trigger expansion for animation export."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from math import isfinite

from svg2ooxml.ir.animation import (
    AnimationDefinition,
    BeginTrigger,
    BeginTriggerType,
)


def _expand_deterministic_repeat_triggers(
    animations: list[AnimationDefinition],
) -> list[AnimationDefinition]:
    """Rewrite integer ``element.repeat(n)`` triggers into absolute offsets.

    This intentionally handles only the narrow deterministic subset that can be
    resolved from authored timing alone. Fractional repeat events, unresolved
    bases, and ambiguous finite-repeat cases are left untouched so later policy
    can reject them explicitly instead of guessing.
    """
    animations_by_id = {
        animation.animation_id: animation
        for animation in animations
        if isinstance(animation.animation_id, str) and animation.animation_id
    }
    if not animations_by_id:
        return animations

    rewritten: list[AnimationDefinition] = []
    for animation in animations:
        timing = animation.timing
        begin_triggers, begin_changed = _rewrite_repeat_trigger_list(
            timing.begin_triggers,
            animations_by_id,
        )
        resolved_begin = _fallback_begin_seconds(begin_triggers, timing.begin)
        end_triggers, end_changed = _rewrite_repeat_trigger_list(
            timing.end_triggers,
            animations_by_id,
            relative_to_seconds=resolved_begin,
        )
        if not begin_changed and not end_changed:
            rewritten.append(animation)
            continue

        new_timing = replace(
            timing,
            begin=resolved_begin,
            begin_triggers=begin_triggers,
            end_triggers=end_triggers,
        )
        raw_attributes = dict(animation.raw_attributes)
        raw_attributes["svg2ooxml_repeat_trigger_expanded"] = "true"
        rewritten.append(
            replace(
                animation,
                timing=new_timing,
                raw_attributes=raw_attributes,
            )
        )
    return rewritten


def _rewrite_repeat_trigger_list(
    triggers: list[BeginTrigger] | None,
    animations_by_id: Mapping[str, AnimationDefinition],
    *,
    relative_to_seconds: float = 0.0,
) -> tuple[list[BeginTrigger] | None, bool]:
    if not triggers:
        return triggers, False

    changed = False
    rewritten: list[BeginTrigger] = []
    for trigger in triggers:
        replacement = _rewrite_repeat_trigger(
            trigger,
            animations_by_id,
            relative_to_seconds=relative_to_seconds,
        )
        if replacement is None:
            rewritten.append(trigger)
            continue
        rewritten.append(replacement)
        changed = True
    return rewritten, changed


def _rewrite_repeat_trigger(
    trigger: BeginTrigger,
    animations_by_id: Mapping[str, AnimationDefinition],
    *,
    relative_to_seconds: float = 0.0,
) -> BeginTrigger | None:
    if trigger.trigger_type is not BeginTriggerType.ELEMENT_REPEAT:
        return None
    if not isinstance(trigger.repeat_iteration, int) or trigger.repeat_iteration < 1:
        return None
    if not isinstance(trigger.target_element_id, str) or not trigger.target_element_id:
        return None

    base_animation = animations_by_id.get(trigger.target_element_id)
    if base_animation is None:
        return None

    base_begin = float(base_animation.timing.begin)
    base_duration = float(base_animation.timing.duration)
    if not isfinite(base_begin) or not isfinite(base_duration) or base_duration <= 0.0:
        return None
    if not _supports_repeat_iteration(base_animation, trigger.repeat_iteration):
        return None

    repeat_time = base_begin + (base_duration * float(trigger.repeat_iteration))
    delay_seconds = repeat_time + float(trigger.delay_seconds) - relative_to_seconds
    if not isfinite(delay_seconds):
        return None

    return BeginTrigger(
        trigger_type=BeginTriggerType.TIME_OFFSET,
        delay_seconds=delay_seconds,
    )


def _supports_repeat_iteration(
    animation: AnimationDefinition,
    repeat_iteration: int,
) -> bool:
    repeat_count = animation.timing.repeat_count
    if repeat_count == "indefinite":
        return True

    raw_repeat_duration = str(animation.raw_attributes.get("repeatDur", "")).strip().lower()
    if raw_repeat_duration == "indefinite":
        return True

    repeat_duration = animation.timing.repeat_duration
    duration = float(animation.timing.duration)
    if isfinite(duration) and duration > 0.0 and repeat_duration is not None:
        return (repeat_iteration * duration) < (repeat_duration - 1e-9)

    try:
        repeat_count_value = int(repeat_count)
    except (TypeError, ValueError):
        return False
    return repeat_iteration < repeat_count_value


def _fallback_begin_seconds(
    triggers: list[BeginTrigger] | None,
    default_begin: float,
) -> float:
    if not triggers:
        return default_begin
    for trigger in triggers:
        if (
            trigger.trigger_type is BeginTriggerType.TIME_OFFSET
            and trigger.target_element_id is None
        ):
            return float(trigger.delay_seconds)
    return default_begin
