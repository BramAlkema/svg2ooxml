"""Rewrite compiled visibility plans to PowerPoint set animations."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    FillMode,
)

from .constants import VISIBILITY_ATTRIBUTES
from .visibility_model import (
    _BLINK_EFFECT,
    _NOOP_ANCHOR_EFFECT,
    _SYNTHETIC_SET_DURATION,
    _VISIBILITY_EFFECT_ATTR,
    CompiledVisibilityPlan,
    coerce_display,
    coerce_visibility,
    element_ancestry,
    is_visible_at_time,
    normalized_visibility_attribute,
    round_time,
    static_property_value,
    times_match,
    xml_identifiers,
)


def plan_to_set_animations(plan: CompiledVisibilityPlan) -> list[AnimationDefinition]:
    compiled: list[AnimationDefinition] = []
    has_future_visible_interval = any(interval.visible for interval in plan.intervals[1:])
    for index, interval in enumerate(plan.intervals):
        if index == 0 and interval.visible:
            continue
        if index == 0 and not interval.visible and has_future_visible_interval:
            continue
        state = "visible" if interval.visible else "hidden"
        compiled.append(
            AnimationDefinition(
                element_id=plan.target_id,
                animation_type=AnimationType.SET,
                target_attribute="style.visibility",
                values=[state],
                timing=AnimationTiming(
                    begin=max(0.0, interval.start),
                    duration=_SYNTHETIC_SET_DURATION,
                    repeat_count=1,
                    fill_mode=FillMode.FREEZE,
                ),
                animation_id=f"svg2ooxml-vis-{plan.target_id}-{index}-{state}",
            )
        )
    return compiled


def plan_to_noop_anchor_animations(
    *,
    visibility_animations: list[AnimationDefinition],
    plans: list[CompiledVisibilityPlan],
    scene_targets: list[tuple[str, etree._Element]],
    xml_lookup: dict[str, etree._Element],
) -> list[AnimationDefinition]:
    planned_target_ids = {plan.target_id for plan in plans}
    anchors: list[AnimationDefinition] = []
    seen_animation_ids: set[str] = set()

    for animation in visibility_animations:
        animation_id = animation.animation_id
        if not isinstance(animation_id, str) or not animation_id:
            continue
        if animation_id in seen_animation_ids:
            continue
        if not _is_noop_visibility_set(animation, xml_lookup=xml_lookup):
            continue

        target_id = _select_noop_anchor_target_id(
            source_element_id=animation.element_id,
            scene_targets=scene_targets,
        )
        if target_id is None:
            continue
        if target_id in planned_target_ids:
            continue

        normalized_attr = normalized_visibility_attribute(animation.target_attribute)
        if normalized_attr == "display":
            target_value = coerce_display(animation.values[-1], "inline")
            visible = target_value != "none"
        else:
            target_value = coerce_visibility(animation.values[-1], "visible")
            visible = target_value == "visible"

        anchors.append(
            AnimationDefinition(
                element_id=target_id,
                animation_type=AnimationType.SET,
                target_attribute="style.visibility",
                values=["visible" if visible else "hidden"],
                timing=AnimationTiming(
                    begin=max(float(animation.timing.begin), 0.0),
                    duration=max(
                        float(animation.timing.duration),
                        _SYNTHETIC_SET_DURATION,
                    ),
                    repeat_count=animation.timing.repeat_count,
                    repeat_duration=animation.timing.repeat_duration,
                    fill_mode=animation.timing.fill_mode,
                    begin_triggers=animation.timing.begin_triggers,
                    end_triggers=animation.timing.end_triggers,
                ),
                animation_id=animation_id,
                additive=animation.additive,
                accumulate=animation.accumulate,
                restart=animation.restart,
                raw_attributes={
                    **animation.raw_attributes,
                    _VISIBILITY_EFFECT_ATTR: _NOOP_ANCHOR_EFFECT,
                },
            )
        )
        seen_animation_ids.add(animation_id)

    return anchors


def plan_to_blink_animation(
    plan: CompiledVisibilityPlan,
    *,
    visibility_animations: list[AnimationDefinition],
    xml_lookup: dict[str, etree._Element],
) -> AnimationDefinition | None:
    target_element = xml_lookup.get(plan.target_id)
    if target_element is None:
        return None
    ancestry = element_ancestry(target_element)
    static_visible = is_visible_at_time(
        ancestry=ancestry,
        animation_map={},
        time=0.0,
    )
    if not static_visible:
        return None

    candidates = [
        animation
        for animation in visibility_animations
        if _is_simple_blink_candidate(animation, target_id=plan.target_id)
        and _plan_matches_blink(plan.intervals, animation)
    ]
    if len(candidates) != 1:
        return None

    candidate = candidates[0]
    return AnimationDefinition(
        element_id=plan.target_id,
        animation_type=AnimationType.SET,
        target_attribute="style.visibility",
        values=["visible"],
        timing=AnimationTiming(
            begin=max(float(candidate.timing.begin), 0.0),
            duration=max(float(candidate.timing.duration), _SYNTHETIC_SET_DURATION),
            repeat_count=candidate.timing.repeat_count,
            repeat_duration=candidate.timing.repeat_duration,
            fill_mode=FillMode.FREEZE,
            begin_triggers=candidate.timing.begin_triggers,
            end_triggers=candidate.timing.end_triggers,
        ),
        animation_id=f"svg2ooxml-vis-{plan.target_id}-blink",
        additive=candidate.additive,
        accumulate=candidate.accumulate,
        restart=candidate.restart,
        raw_attributes={
            **candidate.raw_attributes,
            _VISIBILITY_EFFECT_ATTR: _BLINK_EFFECT,
        },
    )


def _is_noop_visibility_set(
    animation: AnimationDefinition,
    *,
    xml_lookup: dict[str, etree._Element],
) -> bool:
    if animation.animation_type != AnimationType.SET:
        return False
    if not animation.values:
        return False
    normalized_attr = normalized_visibility_attribute(animation.target_attribute)
    if normalized_attr is None:
        return False
    element = xml_lookup.get(animation.element_id)
    if element is None:
        return False

    if normalized_attr == "display":
        static_value = coerce_display(static_property_value(element, "display"), "inline")
        target_value = coerce_display(animation.values[-1], "inline")
    else:
        static_value = coerce_visibility(
            static_property_value(element, "visibility"),
            "visible",
        )
        target_value = coerce_visibility(animation.values[-1], "visible")
    return static_value == target_value


def _select_noop_anchor_target_id(
    *,
    source_element_id: str,
    scene_targets: list[tuple[str, etree._Element]],
) -> str | None:
    for target_id, target_element in scene_targets:
        if any(
            element_id == source_element_id
            for ancestor in element_ancestry(target_element)
            for element_id in xml_identifiers(ancestor)
        ):
            return target_id
    return None


def _is_simple_blink_candidate(
    animation: AnimationDefinition,
    *,
    target_id: str,
) -> bool:
    if animation.animation_type != AnimationType.ANIMATE:
        return False
    if animation.element_id != target_id:
        return False
    if animation.target_attribute not in VISIBILITY_ATTRIBUTES:
        return False
    if len(animation.values) != 2:
        return False
    values = [str(value).strip().lower() for value in animation.values]
    if values[0] not in {"hidden", "collapse"} or values[1] != "visible":
        return False
    if animation.repeat_count not in (None, 1, "1"):
        return False
    if animation.additive.lower() == "sum":
        return False
    triggers = animation.begin_triggers or []
    if len(triggers) > 1:
        return False
    if triggers and triggers[0].trigger_type.value != "time_offset":
        return False
    return animation.duration_ms > 0


def _plan_matches_blink(
    intervals: tuple,
    animation: AnimationDefinition,
) -> bool:
    begin = round_time(max(float(animation.timing.begin), 0.0))
    half = round_time(begin + (max(float(animation.timing.duration), 0.0) / 2.0))
    if half <= begin:
        return False

    idx = 0
    if (
        len(intervals) >= 3
        and intervals[0].visible
        and times_match(intervals[0].start, 0.0)
        and times_match(intervals[0].end, begin)
    ):
        idx = 1

    remaining = intervals[idx:]
    if len(remaining) != 2:
        return False
    hidden, visible = remaining
    return (
        not hidden.visible
        and visible.visible
        and times_match(hidden.start, begin)
        and times_match(hidden.end, half)
        and times_match(visible.start, half)
        and visible.end is None
    )


__all__ = [
    "plan_to_blink_animation",
    "plan_to_noop_anchor_animations",
    "plan_to_set_animations",
]
