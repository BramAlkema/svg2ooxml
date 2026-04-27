"""Shared visibility compiler data types and timing helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass

from lxml import etree

from svg2ooxml.core.styling.style_helpers import parse_style_attr
from svg2ooxml.ir.animation import AnimationDefinition, AnimationType, FillMode

from .constants import (
    DISCRETE_VISIBILITY_ATTRIBUTES,
    DISPLAY_ATTRIBUTES,
    VISIBILITY_ATTRIBUTES,
)

_SOURCE_ID_ATTR = "data-svg2ooxml-source-id"
_ANIMATION_TAGS = frozenset({
    "animate",
    "animateTransform",
    "animateColor",
    "animateMotion",
    "set",
    "mpath",
})
_SYNTHETIC_PREFIX = "svg2ooxml-auto"
_SYNTHETIC_SET_DURATION = 0.001
_TIME_PRECISION = 6
_VISIBILITY_EFFECT_ATTR = "svg2ooxml_visibility_effect"
_BLINK_EFFECT = "blink"
_NOOP_ANCHOR_EFFECT = "noop_anchor"


@dataclass(frozen=True, slots=True)
class VisibilityInterval:
    """Piecewise-constant visibility span for a rendered PowerPoint target."""

    start: float
    end: float | None
    visible: bool


@dataclass(frozen=True, slots=True)
class CompiledVisibilityPlan:
    """Visibility schedule for a rendered PowerPoint target."""

    target_id: str
    intervals: tuple[VisibilityInterval, ...]


def compile_intervals_for_target(
    *,
    target_element: etree._Element,
    visibility_animations: list[AnimationDefinition],
    animation_map: dict[tuple[str, str], list[AnimationDefinition]],
) -> tuple[VisibilityInterval, ...]:
    ancestry = element_ancestry(target_element)
    ancestry_ids = {
        element_id
        for element in ancestry
        for element_id in xml_identifiers(element)
        if element.get("id") == element_id
    }
    relevant_animations = [
        animation
        for animation in visibility_animations
        if animation.element_id in ancestry_ids
    ]
    breakpoints = {0.0}
    for animation in relevant_animations:
        breakpoints.update(animation_breakpoints(animation))

    ordered_breakpoints = sorted(
        round_time(value) for value in breakpoints if math.isfinite(value)
    )
    if not ordered_breakpoints:
        ordered_breakpoints = [0.0]
    if ordered_breakpoints[0] > 0.0:
        ordered_breakpoints.insert(0, 0.0)
    if len(ordered_breakpoints) == 1:
        ordered_breakpoints.append(round_time(ordered_breakpoints[0] + _SYNTHETIC_SET_DURATION))

    sentinel = round_time(ordered_breakpoints[-1] + _SYNTHETIC_SET_DURATION)
    if sentinel <= ordered_breakpoints[-1]:
        sentinel = round_time(ordered_breakpoints[-1] + (_SYNTHETIC_SET_DURATION * 2))
    ordered_breakpoints.append(sentinel)

    intervals: list[VisibilityInterval] = []
    current_visible: bool | None = None
    current_start = 0.0

    for index in range(len(ordered_breakpoints) - 1):
        start = ordered_breakpoints[index]
        end = ordered_breakpoints[index + 1]
        if end <= start:
            continue
        sample_time = start + ((end - start) / 2.0)
        visible = is_visible_at_time(
            ancestry=ancestry,
            animation_map=animation_map,
            time=sample_time,
        )
        if current_visible is None:
            current_visible = visible
            current_start = start
            continue
        if visible != current_visible:
            intervals.append(
                VisibilityInterval(
                    start=current_start,
                    end=start,
                    visible=current_visible,
                )
            )
            current_visible = visible
            current_start = start

    if current_visible is None:
        current_visible = is_visible_at_time(
            ancestry=ancestry,
            animation_map=animation_map,
            time=0.0,
        )
    intervals.append(
        VisibilityInterval(
            start=current_start,
            end=None,
            visible=current_visible,
        )
    )
    return tuple(intervals)


def animation_breakpoints(animation: AnimationDefinition) -> set[float]:
    begin = max(float(animation.timing.begin), 0.0)
    duration = max(float(animation.timing.duration), 0.0)
    breakpoints = {begin}

    if duration <= 0.0:
        return breakpoints

    repeat_cycles = _repeat_cycles(animation)
    local_boundaries = _local_value_boundaries(animation)
    for cycle_index in range(repeat_cycles):
        cycle_start = begin + (cycle_index * duration)
        for boundary in local_boundaries:
            breakpoints.add(cycle_start + (boundary * duration))
        breakpoints.add(cycle_start + duration)
    return breakpoints


def is_visible_at_time(
    *,
    ancestry: list[etree._Element],
    animation_map: dict[tuple[str, str], list[AnimationDefinition]],
    time: float,
) -> bool:
    rendered = True
    inherited_display = "inline"
    inherited_visibility = "visible"

    for element in ancestry:
        element_id = element.get("id")
        inherited_display = _resolve_display(
            element=element,
            element_id=element_id,
            parent_display=inherited_display,
            animation_map=animation_map,
            time=time,
        )
        if inherited_display == "none":
            rendered = False

        inherited_visibility = _resolve_visibility(
            element=element,
            element_id=element_id,
            parent_visibility=inherited_visibility,
            animation_map=animation_map,
            time=time,
        )

    return rendered and inherited_visibility == "visible"


def plan_requires_animation(intervals: tuple[VisibilityInterval, ...]) -> bool:
    if not intervals:
        return False
    if len(intervals) > 1:
        return True
    return not intervals[0].visible


def static_property_value(element: etree._Element, property_name: str) -> str | None:
    value = element.get(property_name)
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    style_value = parse_style_attr(element.get("style")).get(property_name)
    if isinstance(style_value, str) and style_value.strip():
        return style_value.strip().lower()
    return None


def coerce_display(value: str | None, parent_display: str) -> str:
    if value is None or value == "":
        return "inline"
    if value == "inherit":
        return parent_display
    if value == "none":
        return "none"
    return "inline"


def coerce_visibility(value: str | None, parent_visibility: str) -> str:
    if value is None or value == "":
        return parent_visibility
    if value == "inherit":
        return parent_visibility
    if value in {"hidden", "collapse"}:
        return "hidden"
    return "visible"


def element_ancestry(element: etree._Element) -> list[etree._Element]:
    ancestry: list[etree._Element] = []
    current: etree._Element | None = element
    while current is not None:
        ancestry.append(current)
        current = current.getparent()
    ancestry.reverse()
    return ancestry


def xml_identifiers(element: etree._Element) -> list[str]:
    identifiers: list[str] = []
    for attr in ("id", _SOURCE_ID_ATTR):
        value = element.get(attr)
        if isinstance(value, str) and value and value not in identifiers:
            identifiers.append(value)
    return identifiers


def is_visibility_animation(animation: AnimationDefinition) -> bool:
    return (
        animation.animation_type in {AnimationType.ANIMATE, AnimationType.SET}
        and animation.target_attribute in DISCRETE_VISIBILITY_ATTRIBUTES
    )


def normalized_visibility_attribute(attribute: str) -> str | None:
    if attribute in DISPLAY_ATTRIBUTES:
        return "display"
    if attribute in VISIBILITY_ATTRIBUTES:
        return "visibility"
    return None


def round_time(value: float) -> float:
    return round(float(value), _TIME_PRECISION)


def times_match(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return math.isclose(left, right, abs_tol=10 ** (-_TIME_PRECISION))


def _repeat_cycles(animation: AnimationDefinition) -> int:
    repeat_count = animation.repeat_count
    if repeat_count == "indefinite":
        return 1
    try:
        cycles = int(repeat_count)
    except (TypeError, ValueError):
        return 1
    return max(cycles, 1)


def _local_value_boundaries(animation: AnimationDefinition) -> list[float]:
    if animation.animation_type == AnimationType.SET or len(animation.values) <= 1:
        return []
    if animation.key_times:
        return [
            max(0.0, min(1.0, float(boundary)))
            for boundary in animation.key_times[1:]
        ]
    value_count = len(animation.values)
    return [index / value_count for index in range(1, value_count)]


def _resolve_display(
    *,
    element: etree._Element,
    element_id: str | None,
    parent_display: str,
    animation_map: dict[tuple[str, str], list[AnimationDefinition]],
    time: float,
) -> str:
    value = static_property_value(element, "display")
    resolved = coerce_display(value, parent_display)
    if element_id:
        override = _resolve_animation_value(animation_map.get((element_id, "display"), []), time)
        if override is not None:
            resolved = coerce_display(override, parent_display)
    return resolved


def _resolve_visibility(
    *,
    element: etree._Element,
    element_id: str | None,
    parent_visibility: str,
    animation_map: dict[tuple[str, str], list[AnimationDefinition]],
    time: float,
) -> str:
    value = static_property_value(element, "visibility")
    resolved = coerce_visibility(value, parent_visibility)
    if element_id:
        override = _resolve_animation_value(animation_map.get((element_id, "visibility"), []), time)
        if override is not None:
            resolved = coerce_visibility(override, parent_visibility)
    return resolved


def _resolve_animation_value(
    animations: list[AnimationDefinition],
    time: float,
) -> str | None:
    resolved: str | None = None
    for animation in animations:
        value = _animation_value_at_time(animation, time)
        if value is not None:
            resolved = value
    return resolved


def _animation_value_at_time(
    animation: AnimationDefinition,
    time: float,
) -> str | None:
    begin = float(animation.timing.begin)
    if time < begin:
        return None

    duration = max(float(animation.timing.duration), 0.0)
    if animation.animation_type == AnimationType.SET:
        end_time = animation.timing.get_end_time()
        if end_time == float("inf") or time < end_time:
            return animation.values[-1]
        if animation.timing.fill_mode == FillMode.FREEZE:
            return animation.values[-1]
        return None

    if duration <= 0.0:
        return animation.values[-1] if animation.timing.fill_mode == FillMode.FREEZE else None

    repeat_count = animation.repeat_count
    elapsed = time - begin
    if repeat_count == "indefinite":
        local_progress = (elapsed % duration) / duration
        return _discrete_value_at_progress(animation, local_progress)

    try:
        cycles = max(int(repeat_count), 1)
    except (TypeError, ValueError):
        cycles = 1

    total_duration = duration * cycles
    if elapsed >= total_duration:
        if animation.timing.fill_mode == FillMode.FREEZE:
            return animation.values[-1]
        return None

    local_progress = (elapsed % duration) / duration
    return _discrete_value_at_progress(animation, local_progress)


def _discrete_value_at_progress(
    animation: AnimationDefinition,
    progress: float,
) -> str:
    if len(animation.values) == 1:
        return animation.values[0]

    progress = max(0.0, min(1.0, progress))
    if animation.key_times:
        value_index = 0
        for index, boundary in enumerate(animation.key_times):
            if progress + 1e-9 >= boundary:
                value_index = index
        return animation.values[min(value_index, len(animation.values) - 1)]

    value_index = min(int(progress * len(animation.values)), len(animation.values) - 1)
    return animation.values[value_index]


__all__ = [
    "CompiledVisibilityPlan",
    "VisibilityInterval",
    "_ANIMATION_TAGS",
    "_BLINK_EFFECT",
    "_NOOP_ANCHOR_EFFECT",
    "_SOURCE_ID_ATTR",
    "_SYNTHETIC_PREFIX",
    "_SYNTHETIC_SET_DURATION",
    "_VISIBILITY_EFFECT_ATTR",
    "coerce_display",
    "coerce_visibility",
    "compile_intervals_for_target",
    "element_ancestry",
    "is_visibility_animation",
    "is_visible_at_time",
    "normalized_visibility_attribute",
    "plan_requires_animation",
    "round_time",
    "static_property_value",
    "times_match",
    "xml_identifiers",
]
