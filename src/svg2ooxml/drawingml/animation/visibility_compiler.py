"""Compile SVG display/visibility semantics into PowerPoint visibility plans."""

from __future__ import annotations

import math
from dataclasses import dataclass

from lxml import etree

from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.core.parser.xml_utils import walk
from svg2ooxml.core.styling.style_helpers import parse_style_attr
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    FillMode,
)
from svg2ooxml.ir.scene import Group, Scene

from .constants import (
    DISCRETE_VISIBILITY_ATTRIBUTES,
    DISPLAY_ATTRIBUTES,
    VISIBILITY_ATTRIBUTES,
)

__all__ = [
    "CompiledVisibilityPlan",
    "VisibilityInterval",
    "assign_missing_visibility_source_ids",
    "compile_visibility_plans",
    "rewrite_visibility_animations",
]

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


def assign_missing_visibility_source_ids(
    svg_root: etree._Element,
    *,
    prefix: str = _SYNTHETIC_PREFIX,
) -> int:
    """Assign stable source identifiers to anonymous SVG elements.

    The compiler only needs a stable source identifier for mapping authored SVG
    elements onto converted IR leaves. Using ``data-svg2ooxml-source-id`` keeps
    those identifiers out of the SVG's authored ``id`` namespace.
    """

    existing_ids: set[str] = set()
    for element in walk(svg_root):
        for attr in ("id", _SOURCE_ID_ATTR):
            value = element.get(attr)
            if isinstance(value, str) and value:
                existing_ids.add(value)

    assigned = 0
    counter = 0
    for element in walk(svg_root):
        if local_name(element.tag) in _ANIMATION_TAGS:
            continue
        if element.get("id") or element.get(_SOURCE_ID_ATTR):
            continue
        synthetic_id = f"{prefix}-{counter}"
        while synthetic_id in existing_ids:
            counter += 1
            synthetic_id = f"{prefix}-{counter}"
        element.set(_SOURCE_ID_ATTR, synthetic_id)
        existing_ids.add(synthetic_id)
        assigned += 1
        counter += 1
    return assigned


def rewrite_visibility_animations(
    animations: list[AnimationDefinition],
    scene: Scene,
    svg_root: etree._Element | None,
) -> list[AnimationDefinition]:
    """Replace authored display/visibility animations with native visibility sets."""

    if svg_root is None:
        return animations

    xml_lookup = _build_xml_lookup(svg_root)
    scene_targets = _resolve_scene_targets(scene, xml_lookup)
    plans = compile_visibility_plans(animations, scene, svg_root)
    visibility_animations = [
        animation for animation in animations if _is_visibility_animation(animation)
    ]

    rewritten = [
        animation for animation in animations if not _is_visibility_animation(animation)
    ]
    for plan in plans:
        blink = _plan_to_blink_animation(
            plan,
            visibility_animations=visibility_animations,
            xml_lookup=xml_lookup,
        )
        if blink is not None:
            rewritten.append(blink)
            continue
        rewritten.extend(_plan_to_set_animations(plan))
    rewritten.extend(
        _plan_to_noop_anchor_animations(
            visibility_animations=visibility_animations,
            plans=plans,
            scene_targets=scene_targets,
            xml_lookup=xml_lookup,
        )
    )
    if rewritten:
        return rewritten
    return rewritten


def compile_visibility_plans(
    animations: list[AnimationDefinition],
    scene: Scene,
    svg_root: etree._Element,
) -> list[CompiledVisibilityPlan]:
    """Compile per-shape visibility plans from authored SVG semantics."""

    visibility_animations = [
        animation for animation in animations if _is_visibility_animation(animation)
    ]
    xml_lookup = _build_xml_lookup(svg_root)
    scene_targets = _resolve_scene_targets(scene, xml_lookup)
    if not scene_targets:
        return []

    animation_map: dict[tuple[str, str], list[AnimationDefinition]] = {}
    for animation in visibility_animations:
        normalized_attr = _normalized_visibility_attribute(animation.target_attribute)
        if normalized_attr is None:
            continue
        animation_map.setdefault((animation.element_id, normalized_attr), []).append(animation)

    plans: list[CompiledVisibilityPlan] = []
    for target_id, target_element in scene_targets:
        intervals = _compile_intervals_for_target(
            target_element=target_element,
            visibility_animations=visibility_animations,
            animation_map=animation_map,
        )
        if _plan_requires_animation(intervals):
            plans.append(CompiledVisibilityPlan(target_id=target_id, intervals=intervals))
    return plans


def _build_xml_lookup(svg_root: etree._Element) -> dict[str, etree._Element]:
    lookup: dict[str, etree._Element] = {}
    for element in walk(svg_root):
        for attr in ("id", _SOURCE_ID_ATTR):
            value = element.get(attr)
            if isinstance(value, str) and value and value not in lookup:
                lookup[value] = element
    return lookup


def _resolve_scene_targets(
    scene: Scene,
    xml_lookup: dict[str, etree._Element],
) -> list[tuple[str, etree._Element]]:
    resolved: list[tuple[str, etree._Element]] = []
    seen: set[str] = set()

    def visit(element: object) -> None:
        if isinstance(element, Group):
            for child in element.children:
                visit(child)
            return

        target_id = _select_target_id(element, xml_lookup)
        if target_id is None or target_id in seen:
            return
        target_element = xml_lookup.get(target_id)
        if target_element is None:
            return
        seen.add(target_id)
        resolved.append((target_id, target_element))

    for element in scene.elements:
        visit(element)

    return resolved


def _select_target_id(
    element: object,
    xml_lookup: dict[str, etree._Element],
) -> str | None:
    metadata = getattr(element, "metadata", None)
    metadata_ids: list[str] = []
    if isinstance(metadata, dict):
        raw_ids = metadata.get("element_ids", [])
        if isinstance(raw_ids, list):
            for value in raw_ids:
                if isinstance(value, str) and value and value not in metadata_ids:
                    metadata_ids.append(value)

    explicit_id = getattr(element, "element_id", None)
    if isinstance(explicit_id, str) and explicit_id:
        candidates = [explicit_id] + [value for value in metadata_ids if value != explicit_id]
    else:
        candidates = metadata_ids

    for candidate in candidates:
        target_element = xml_lookup.get(candidate)
        if target_element is not None and target_element.get("id") == candidate:
            return candidate
    for candidate in candidates:
        if candidate in xml_lookup:
            return candidate
    return None


def _compile_intervals_for_target(
    *,
    target_element: etree._Element,
    visibility_animations: list[AnimationDefinition],
    animation_map: dict[tuple[str, str], list[AnimationDefinition]],
) -> tuple[VisibilityInterval, ...]:
    ancestry = _element_ancestry(target_element)
    ancestry_ids = {
        element_id
        for element in ancestry
        for element_id in _xml_identifiers(element)
        if element.get("id") == element_id
    }
    relevant_animations = [
        animation
        for animation in visibility_animations
        if animation.element_id in ancestry_ids
    ]
    breakpoints = {0.0}
    for animation in relevant_animations:
        breakpoints.update(_animation_breakpoints(animation))

    ordered_breakpoints = sorted(_round_time(value) for value in breakpoints if math.isfinite(value))
    if not ordered_breakpoints:
        ordered_breakpoints = [0.0]
    if ordered_breakpoints[0] > 0.0:
        ordered_breakpoints.insert(0, 0.0)
    if len(ordered_breakpoints) == 1:
        ordered_breakpoints.append(_round_time(ordered_breakpoints[0] + _SYNTHETIC_SET_DURATION))

    sentinel = _round_time(ordered_breakpoints[-1] + _SYNTHETIC_SET_DURATION)
    if sentinel <= ordered_breakpoints[-1]:
        sentinel = _round_time(ordered_breakpoints[-1] + (_SYNTHETIC_SET_DURATION * 2))
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
        visible = _is_visible_at_time(
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
        current_visible = _is_visible_at_time(
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


def _animation_breakpoints(animation: AnimationDefinition) -> set[float]:
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


def _is_visible_at_time(
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


def _resolve_display(
    *,
    element: etree._Element,
    element_id: str | None,
    parent_display: str,
    animation_map: dict[tuple[str, str], list[AnimationDefinition]],
    time: float,
) -> str:
    value = _static_property_value(element, "display")
    resolved = _coerce_display(value, parent_display)
    if element_id:
        override = _resolve_animation_value(animation_map.get((element_id, "display"), []), time)
        if override is not None:
            resolved = _coerce_display(override, parent_display)
    return resolved


def _resolve_visibility(
    *,
    element: etree._Element,
    element_id: str | None,
    parent_visibility: str,
    animation_map: dict[tuple[str, str], list[AnimationDefinition]],
    time: float,
) -> str:
    value = _static_property_value(element, "visibility")
    resolved = _coerce_visibility(value, parent_visibility)
    if element_id:
        override = _resolve_animation_value(animation_map.get((element_id, "visibility"), []), time)
        if override is not None:
            resolved = _coerce_visibility(override, parent_visibility)
    return resolved


def _static_property_value(element: etree._Element, property_name: str) -> str | None:
    value = element.get(property_name)
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    style_value = parse_style_attr(element.get("style")).get(property_name)
    if isinstance(style_value, str) and style_value.strip():
        return style_value.strip().lower()
    return None


def _coerce_display(value: str | None, parent_display: str) -> str:
    if value is None or value == "":
        return "inline"
    if value == "inherit":
        return parent_display
    if value == "none":
        return "none"
    return "inline"


def _coerce_visibility(value: str | None, parent_visibility: str) -> str:
    if value is None or value == "":
        return parent_visibility
    if value == "inherit":
        return parent_visibility
    if value in {"hidden", "collapse"}:
        return "hidden"
    return "visible"


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


def _plan_requires_animation(intervals: tuple[VisibilityInterval, ...]) -> bool:
    if not intervals:
        return False
    if len(intervals) > 1:
        return True
    return not intervals[0].visible


def _plan_to_set_animations(plan: CompiledVisibilityPlan) -> list[AnimationDefinition]:
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


def _plan_to_noop_anchor_animations(
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

        normalized_attr = _normalized_visibility_attribute(animation.target_attribute)
        if normalized_attr == "display":
            target_value = _coerce_display(animation.values[-1], "inline")
            visible = target_value != "none"
        else:
            target_value = _coerce_visibility(animation.values[-1], "visible")
            visible = target_value == "visible"

        anchors.append(
            AnimationDefinition(
                element_id=target_id,
                animation_type=AnimationType.SET,
                target_attribute="style.visibility",
                values=["visible" if visible else "hidden"],
                timing=AnimationTiming(
                    begin=max(float(animation.timing.begin), 0.0),
                    duration=max(float(animation.timing.duration), _SYNTHETIC_SET_DURATION),
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


def _plan_to_blink_animation(
    plan: CompiledVisibilityPlan,
    *,
    visibility_animations: list[AnimationDefinition],
    xml_lookup: dict[str, etree._Element],
) -> AnimationDefinition | None:
    target_element = xml_lookup.get(plan.target_id)
    if target_element is None:
        return None
    ancestry = _element_ancestry(target_element)
    static_visible = _is_visible_at_time(
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
    normalized_attr = _normalized_visibility_attribute(animation.target_attribute)
    if normalized_attr is None:
        return False
    element = xml_lookup.get(animation.element_id)
    if element is None:
        return False

    if normalized_attr == "display":
        static_value = _coerce_display(_static_property_value(element, "display"), "inline")
        target_value = _coerce_display(animation.values[-1], "inline")
    else:
        static_value = _coerce_visibility(
            _static_property_value(element, "visibility"),
            "visible",
        )
        target_value = _coerce_visibility(animation.values[-1], "visible")
    return static_value == target_value


def _select_noop_anchor_target_id(
    *,
    source_element_id: str,
    scene_targets: list[tuple[str, etree._Element]],
) -> str | None:
    for target_id, target_element in scene_targets:
        if any(
            element_id == source_element_id
            for ancestor in _element_ancestry(target_element)
            for element_id in _xml_identifiers(ancestor)
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
    intervals: tuple[VisibilityInterval, ...],
    animation: AnimationDefinition,
) -> bool:
    begin = _round_time(max(float(animation.timing.begin), 0.0))
    half = _round_time(begin + (max(float(animation.timing.duration), 0.0) / 2.0))
    if half <= begin:
        return False

    idx = 0
    if (
        len(intervals) >= 3
        and intervals[0].visible
        and _times_match(intervals[0].start, 0.0)
        and _times_match(intervals[0].end, begin)
    ):
        idx = 1

    remaining = intervals[idx:]
    if len(remaining) != 2:
        return False
    hidden, visible = remaining
    return (
        not hidden.visible
        and visible.visible
        and _times_match(hidden.start, begin)
        and _times_match(hidden.end, half)
        and _times_match(visible.start, half)
        and visible.end is None
    )


def _element_ancestry(element: etree._Element) -> list[etree._Element]:
    ancestry: list[etree._Element] = []
    current: etree._Element | None = element
    while current is not None:
        ancestry.append(current)
        current = current.getparent()
    ancestry.reverse()
    return ancestry


def _xml_identifiers(element: etree._Element) -> list[str]:
    identifiers: list[str] = []
    for attr in ("id", _SOURCE_ID_ATTR):
        value = element.get(attr)
        if isinstance(value, str) and value and value not in identifiers:
            identifiers.append(value)
    return identifiers


def _is_visibility_animation(animation: AnimationDefinition) -> bool:
    return (
        animation.animation_type in {AnimationType.ANIMATE, AnimationType.SET}
        and animation.target_attribute in DISCRETE_VISIBILITY_ATTRIBUTES
    )


def _normalized_visibility_attribute(attribute: str) -> str | None:
    if attribute in DISPLAY_ATTRIBUTES:
        return "display"
    if attribute in VISIBILITY_ATTRIBUTES:
        return "visibility"
    return None


def _round_time(value: float) -> float:
    return round(float(value), _TIME_PRECISION)


def _times_match(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return math.isclose(left, right, abs_tol=10 ** (-_TIME_PRECISION))
