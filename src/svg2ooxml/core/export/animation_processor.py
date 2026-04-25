"""Animation serialization helpers, enrichment, and sampled center motion composition."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from math import isfinite
from typing import Any

from svg2ooxml.core.export.motion_geometry import (
    _build_sampled_motion_replacement,
    _image_local_layout,
    _infer_element_heading_deg,
    _inverse_project_affine_point,
    _inverse_project_affine_rect,
    _lerp,
    _parse_sampled_motion_points,
    _project_affine_point,
    _resolve_affine_matrix,
    _rotate_point,
    _sample_polyline_at_fraction,
    _sample_progress_values,
    _translate_element_to_center_target,
)
from svg2ooxml.core.ir.converter import IRScene
from svg2ooxml.drawingml.animation.native_matcher import (
    NativeAnimationMatch,
    classify_native_animation,
)
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationScene,
    AnimationSummary,
    AnimationTiming,
    AnimationType,
    BeginTrigger,
    BeginTriggerType,
    CalcMode,
    TransformType,
)

# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _build_animation_metadata(
    animations: list[AnimationDefinition],
    timeline_scenes: list[AnimationScene],
    summary: AnimationSummary | None,
    fallback_reasons: Mapping[str, int] | None,
    policy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    summary_dict = _serialize_animation_summary(summary, fallback_reasons=fallback_reasons)
    timeline_payload = [_serialize_timeline_scene(scene) for scene in timeline_scenes]
    native_matches = [classify_native_animation(defn) for defn in animations]
    payload = {
        "definition_count": len(animations),
        "definitions": [
            _serialize_animation_definition(defn, native_match)
            for defn, native_match in zip(animations, native_matches, strict=True)
        ],
        "timeline": timeline_payload,
        "summary": summary_dict,
        "native_match_summary": _serialize_native_match_summary(native_matches),
    }
    if policy:
        payload["policy"] = dict(policy)
    return payload


def _serialize_animation_definition(
    definition: AnimationDefinition,
    native_match: NativeAnimationMatch | None = None,
) -> dict[str, Any]:
    native_match = native_match or classify_native_animation(definition)
    return {
        "element_id": definition.element_id,
        "animation_type": definition.animation_type.value,
        "target_attribute": definition.target_attribute,
        "values": list(definition.values),
        "native_match": native_match.to_dict(),
        "timing": _serialize_animation_timing(definition.timing),
        "attribute_type": definition.attribute_type,
        "from_value": definition.from_value,
        "to_value": definition.to_value,
        "by_value": definition.by_value,
        "key_times": list(definition.key_times) if definition.key_times else None,
        "key_points": list(definition.key_points) if definition.key_points else None,
        "key_splines": [list(spline) for spline in definition.key_splines] if definition.key_splines else None,
        "calc_mode": definition.calc_mode.value if isinstance(definition.calc_mode, CalcMode) else definition.calc_mode,
        "transform_type": definition.transform_type.value if definition.transform_type else None,
        "additive": definition.additive,
        "accumulate": definition.accumulate,
        "restart": definition.restart,
        "min_ms": definition.min_ms,
        "max_ms": definition.max_ms,
        "raw_attributes": dict(definition.raw_attributes),
        "element_heading_deg": definition.element_heading_deg,
        "motion_space_matrix": list(definition.motion_space_matrix) if definition.motion_space_matrix else None,
        "element_motion_offset_px": list(definition.element_motion_offset_px) if definition.element_motion_offset_px else None,
        "motion_viewport_px": list(definition.motion_viewport_px) if definition.motion_viewport_px else None,
    }


def _serialize_native_match_summary(
    native_matches: list[NativeAnimationMatch],
) -> dict[str, Any]:
    by_level: Counter[str] = Counter(match.level.value for match in native_matches)
    by_reason: Counter[str] = Counter(match.reason for match in native_matches)
    by_required_evidence: Counter[str] = Counter(
        tier
        for match in native_matches
        for tier in match.required_evidence_tiers
    )
    return {
        "total": len(native_matches),
        "by_level": dict(sorted(by_level.items())),
        "by_reason": dict(sorted(by_reason.items())),
        "by_required_evidence": dict(sorted(by_required_evidence.items())),
        "mimic_allowed_count": sum(1 for match in native_matches if match.mimic_allowed),
        "oracle_required_count": sum(1 for match in native_matches if match.oracle_required),
        "visual_required_count": sum(1 for match in native_matches if match.visual_required),
    }


def _serialize_animation_timing(timing: AnimationTiming) -> dict[str, Any]:
    return {
        "begin": timing.begin,
        "duration": timing.duration,
        "repeat_count": timing.repeat_count,
        "repeat_duration": timing.repeat_duration,
        "fill_mode": timing.fill_mode.value,
        "begin_triggers": [
            _serialize_begin_trigger(trigger)
            for trigger in (timing.begin_triggers or [])
        ],
        "end_triggers": [
            _serialize_begin_trigger(trigger)
            for trigger in (timing.end_triggers or [])
        ],
    }


def _serialize_begin_trigger(trigger: Any) -> dict[str, Any]:
    return {
        "trigger_type": trigger.trigger_type.value,
        "delay_seconds": trigger.delay_seconds,
        "target_element_id": trigger.target_element_id,
        "event_name": getattr(trigger, "event_name", None),
        "repeat_iteration": getattr(trigger, "repeat_iteration", None),
        "access_key": getattr(trigger, "access_key", None),
        "wallclock_value": getattr(trigger, "wallclock_value", None),
    }


def _serialize_animation_summary(
    summary: AnimationSummary | None,
    *,
    fallback_reasons: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    if summary is None:
        return {
            "total_animations": 0,
            "complexity": "simple",
            "duration": 0.0,
            "has_transforms": False,
            "has_motion_paths": False,
            "has_color_animations": False,
            "has_easing": False,
            "has_sequences": False,
            "element_count": 0,
            "warnings": [],
            "fallback_reasons": {},
        }

    return {
        "total_animations": summary.total_animations,
        "complexity": summary.complexity.value,
        "duration": summary.duration,
        "has_transforms": summary.has_transforms,
        "has_motion_paths": summary.has_motion_paths,
        "has_color_animations": summary.has_color_animations,
        "has_easing": summary.has_easing,
        "has_sequences": summary.has_sequences,
        "element_count": summary.element_count,
        "warnings": list(summary.warnings),
        "fallback_reasons": dict(fallback_reasons or {}),
    }


def _serialize_timeline_scene(scene: AnimationScene) -> dict[str, Any]:
    return {
        "time": scene.time,
        "element_states": {element_id: dict(properties) for element_id, properties in scene.element_states.items()},
    }


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


# ---------------------------------------------------------------------------
# Predicate helpers
# ---------------------------------------------------------------------------


def _single_matching_member(
    members: list[tuple[int, AnimationDefinition]],
    predicate,
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


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------


def _parse_scale_bounds(
    animation: AnimationDefinition,
) -> tuple[tuple[float, float], tuple[float, float]]:
    from svg2ooxml.common.conversions.transforms import parse_scale_pair

    return (
        parse_scale_pair(animation.values[0]),
        parse_scale_pair(animation.values[-1]),
    )


def _parse_rotate_bounds(animation: AnimationDefinition) -> tuple[float, float]:
    from svg2ooxml.common.conversions.transforms import parse_numeric_list

    start_numbers = parse_numeric_list(animation.values[0])
    end_numbers = parse_numeric_list(animation.values[-1])
    start_angle = start_numbers[0] if start_numbers else 0.0
    end_angle = end_numbers[0] if end_numbers else start_angle
    return (start_angle, end_angle)


def _parse_rotate_keyframes(
    animation: AnimationDefinition,
) -> tuple[list[float], tuple[float, float] | None]:
    from svg2ooxml.common.conversions.transforms import parse_numeric_list

    angles: list[float] = []
    center: tuple[float, float] | None = None
    for value in animation.values:
        numbers = parse_numeric_list(value)
        if numbers:
            angles.append(numbers[0])
        else:
            angles.append(0.0)
        if len(numbers) >= 3:
            parsed_center = (numbers[1], numbers[2])
            if center is None:
                center = parsed_center
            elif (
                abs(center[0] - parsed_center[0]) > 1e-6
                or abs(center[1] - parsed_center[1]) > 1e-6
            ):
                return (angles, center)
    return (angles, center)


def _interpolate_numeric_keyframes(
    values: list[float],
    key_times: list[float] | None,
    fraction: float,
) -> float:
    if not values:
        return 0.0
    if len(values) == 1 or fraction <= 0.0:
        return values[0]
    if fraction >= 1.0:
        return values[-1]

    if key_times and len(key_times) == len(values):
        for index in range(len(key_times) - 1):
            if fraction <= key_times[index + 1]:
                span = max(1e-9, key_times[index + 1] - key_times[index])
                local_t = (fraction - key_times[index]) / span
                return _lerp(values[index], values[index + 1], local_t)
        return values[-1]

    position = fraction * (len(values) - 1)
    index = min(int(position), len(values) - 2)
    local_t = position - index
    return _lerp(values[index], values[index + 1], local_t)


def _interpolate_pair_keyframes(
    values: list[tuple[float, float]],
    key_times: list[float] | None,
    fraction: float,
) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    xs = [pair[0] for pair in values]
    ys = [pair[1] for pair in values]
    return (
        _interpolate_numeric_keyframes(xs, key_times, fraction),
        _interpolate_numeric_keyframes(ys, key_times, fraction),
    )


def _rotate_around_point(
    point: tuple[float, float],
    center: tuple[float, float],
    angle_deg: float,
) -> tuple[float, float]:
    local_x = point[0] - center[0]
    local_y = point[1] - center[1]
    rotated_x, rotated_y = _rotate_point((local_x, local_y), angle_deg)
    return (center[0] + rotated_x, center[1] + rotated_y)


def _numeric_bounds(
    member: tuple[int, AnimationDefinition] | None,
    *,
    default: float,
) -> tuple[float, float]:
    if member is None:
        return (default, default)
    try:
        return (float(member[1].values[0]), float(member[1].values[-1]))
    except (TypeError, ValueError):
        return (default, default)


def _parse_translate_pair(value: str) -> tuple[float, float]:
    from svg2ooxml.common.conversions.transforms import parse_translation_pair

    return parse_translation_pair(value)


# ---------------------------------------------------------------------------
# Grouping key helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Element enrichment
# ---------------------------------------------------------------------------


def _enrich_animations_with_element_centers(
    animations: list[AnimationDefinition],
    scene: IRScene,
) -> list[AnimationDefinition]:
    """Populate geometry-derived animation metadata from scene graph bounds.

    This is needed so the rotate handler can compute orbital motion paths when
    the SVG rotation center (cx, cy) differs from the shape center, and so
    motion paths can be shifted into the absolute ``ppt_x``/``ppt_y`` space
    that PowerPoint stores in ``<p:animMotion path="...">``.
    """
    from dataclasses import replace as _replace

    from svg2ooxml.ir.scene import Group
    from svg2ooxml.ir.text import TextFrame

    bbox_map: dict[str, tuple[float, float, float, float]] = {}
    center_map: dict[str, tuple[float, float]] = {}
    heading_map: dict[str, float] = {}
    text_origin_map: dict[str, tuple[float, float]] = {}

    def _walk(elements: list) -> None:
        for el in elements:
            meta = getattr(el, "metadata", None)
            bbox = getattr(el, "bbox", None)
            if isinstance(meta, dict):
                for eid in meta.get("element_ids", []):
                    if not isinstance(eid, str) or bbox is None:
                        continue
                    bbox_map.setdefault(
                        eid,
                        (bbox.x, bbox.y, bbox.width, bbox.height),
                    )
                    center_map.setdefault(
                        eid,
                        (bbox.x + bbox.width / 2.0, bbox.y + bbox.height / 2.0),
                    )
                    heading = _infer_element_heading_deg(el)
                    if heading is not None:
                        heading_map.setdefault(eid, heading)
                    if isinstance(el, TextFrame):
                        text_origin_map.setdefault(
                            eid,
                            (el.origin.x, el.origin.y),
                        )
            if isinstance(el, Group):
                _walk(getattr(el, "children", []))

    _walk(scene.elements)

    enriched = []
    viewport_size = None
    if getattr(scene, "width_px", None) and getattr(scene, "height_px", None):
        viewport_size = (float(scene.width_px), float(scene.height_px))
    for anim in animations:
        if (
            anim.transform_type in {TransformType.ROTATE, TransformType.SCALE}
            and anim.element_center_px is None
            and anim.element_id in center_map
        ):
            anim = _replace(anim, element_center_px=center_map[anim.element_id])
        if anim.element_heading_deg is None and anim.element_id in heading_map:
            anim = _replace(anim, element_heading_deg=heading_map[anim.element_id])
        if (
            anim.animation_type == AnimationType.ANIMATE_MOTION
            and anim.element_motion_offset_px is None
            and anim.element_id in bbox_map
        ):
            bbox_x, bbox_y, _, _ = bbox_map[anim.element_id]
            if anim.element_id in text_origin_map:
                origin_x, origin_y = text_origin_map[anim.element_id]
            elif anim.motion_space_matrix is not None:
                origin_x = anim.motion_space_matrix[4]
                origin_y = anim.motion_space_matrix[5]
            else:
                origin_x = 0.0
                origin_y = 0.0
            anim = _replace(
                anim,
                element_motion_offset_px=(bbox_x - origin_x, bbox_y - origin_y),
            )
        if anim.motion_viewport_px is None and viewport_size is not None:
            anim = _replace(anim, motion_viewport_px=viewport_size)
        enriched.append(anim)
    return enriched


def _lower_safe_group_transform_targets_with_animated_descendants(
    animations: list[AnimationDefinition],
    scene: IRScene,
) -> list[AnimationDefinition]:
    """Lower safe parent-group motion when descendants animate too.

    PowerPoint handles ``grpSp`` motion reliably only when the group is the
    sole animated target in that subtree. Once descendants also animate, the
    grouped playback becomes brittle and our descendant-mimic attempts have not
    held up empirically.

    Keep the fallback intentionally narrow: translate-only group motion can be
    cloned onto renderable leaf descendants while the group is flattened, but
    rotate/scale/matrix group transforms are dropped in mixed subtrees. This
    preserves descendant-local effects and avoids preserving an animated
    ``grpSp`` that PowerPoint renders incorrectly.
    """

    from svg2ooxml.ir.scene import Group

    group_leaf_ids: dict[str, tuple[str, ...]] = {}
    group_descendant_ids: dict[str, tuple[str, ...]] = {}

    def _element_ids(element: object) -> tuple[str, ...]:
        meta = getattr(element, "metadata", None)
        if not isinstance(meta, dict):
            return ()
        return tuple(
            dict.fromkeys(
                eid for eid in meta.get("element_ids", []) if isinstance(eid, str) and eid
            )
        )

    def _leaf_element_ids(element: object) -> tuple[str, ...]:
        if isinstance(element, Group):
            collected: list[str] = []
            for child in element.children:
                collected.extend(_leaf_element_ids(child))
            return tuple(dict.fromkeys(collected))
        return _element_ids(element)

    def _all_descendant_ids(element: object) -> tuple[str, ...]:
        collected: list[str] = []
        collected.extend(_element_ids(element))
        if isinstance(element, Group):
            for child in element.children:
                collected.extend(_all_descendant_ids(child))
        return tuple(dict.fromkeys(collected))

    def _walk(elements: list[object]) -> None:
        for element in elements:
            if not isinstance(element, Group):
                continue
            group_ids = _element_ids(element)
            if group_ids:
                leaf_ids = _leaf_element_ids(element)
                descendant_ids = _all_descendant_ids(element)
                for group_id in group_ids:
                    group_leaf_ids[group_id] = tuple(
                        eid for eid in leaf_ids if eid != group_id
                    )
                    group_descendant_ids[group_id] = tuple(
                        eid for eid in descendant_ids if eid != group_id
                    )
            _walk(list(getattr(element, "children", [])))

    _walk(list(scene.elements))

    if not group_descendant_ids:
        return animations

    animated_ids = {
        animation.element_id
        for animation in animations
        if isinstance(animation.element_id, str) and animation.element_id
    }

    mixed_group_ids = {
        group_id
        for group_id, descendant_ids in group_descendant_ids.items()
        if any(descendant_id in animated_ids for descendant_id in descendant_ids)
    }
    if not mixed_group_ids:
        return animations

    lowered: list[AnimationDefinition] = []
    for animation in animations:
        if (
            animation.animation_type != AnimationType.ANIMATE_TRANSFORM
            or animation.transform_type is None
            or animation.element_id not in mixed_group_ids
        ):
            lowered.append(animation)
            continue

        if animation.transform_type != TransformType.TRANSLATE:
            continue

        for leaf_id in group_leaf_ids.get(animation.element_id, ()):
            raw_attributes = dict(animation.raw_attributes)
            raw_attributes["svg2ooxml_group_transform_split"] = animation.element_id
            raw_attributes["svg2ooxml_group_transform_expanded"] = animation.element_id
            clone_animation_id = (
                f"{animation.animation_id}__{leaf_id}"
                if isinstance(animation.animation_id, str) and animation.animation_id
                else None
            )
            lowered.append(
                replace(
                    animation,
                    element_id=leaf_id,
                    animation_id=clone_animation_id,
                    raw_attributes=raw_attributes,
                )
            )
    return lowered


def _group_transform_clone_origin(animation: AnimationDefinition) -> str | None:
    for key in (
        "svg2ooxml_group_transform_split",
        "svg2ooxml_group_transform_expanded",
    ):
        origin = animation.raw_attributes.get(key)
        if isinstance(origin, str) and origin:
            return origin
    return None


def _prepare_scene_for_native_opacity_effects(
    scene: IRScene,
    animations: list[AnimationDefinition],
) -> None:
    """Remove baked static alpha for targets driven by native opacity effects."""
    from dataclasses import replace as _replace

    from svg2ooxml.ir.paint import LinearGradientPaint, RadialGradientPaint, SolidPaint
    from svg2ooxml.ir.scene import Group

    target_ids = {
        animation.element_id
        for animation in animations
        if _needs_unbaked_native_opacity_effect(animation)
    }
    if not target_ids:
        return

    def _reset_paint_alpha(paint: object, baked_opacity: float) -> object:
        if isinstance(paint, SolidPaint):
            if abs(float(paint.opacity) - baked_opacity) <= 1e-6:
                return _replace(paint, opacity=1.0)
            return paint
        if isinstance(paint, (LinearGradientPaint, RadialGradientPaint)):
            if paint.stops and all(abs(float(stop.opacity) - baked_opacity) <= 1e-6 for stop in paint.stops):
                return _replace(
                    paint,
                    stops=[
                        _replace(stop, opacity=1.0)
                        for stop in paint.stops
                    ],
                )
        return paint

    def _walk(elements: list[object]) -> list[object]:
        updated_elements: list[object] = []
        for element in elements:
            if isinstance(element, Group):
                updated_elements.append(
                    _replace(element, children=_walk(list(element.children)))
                )
                continue

            metadata = getattr(element, "metadata", None)
            element_ids = (
                [eid for eid in metadata.get("element_ids", []) if isinstance(eid, str)]
                if isinstance(metadata, dict)
                else []
            )
            if not any(element_id in target_ids for element_id in element_ids):
                updated_elements.append(element)
                continue

            baked_opacity = float(getattr(element, "opacity", 1.0))
            kwargs: dict[str, object] = {}
            fill = getattr(element, "fill", None)
            if fill is not None:
                reset_fill = _reset_paint_alpha(fill, baked_opacity)
                if reset_fill is not fill:
                    kwargs["fill"] = reset_fill
            stroke = getattr(element, "stroke", None)
            if stroke is not None and getattr(stroke, "paint", None) is not None:
                reset_stroke_paint = _reset_paint_alpha(stroke.paint, baked_opacity)
                if reset_stroke_paint is not stroke.paint or abs(float(stroke.opacity) - baked_opacity) <= 1e-6:
                    kwargs["stroke"] = _replace(
                        stroke,
                        paint=reset_stroke_paint,
                        opacity=(1.0 if abs(float(stroke.opacity) - baked_opacity) <= 1e-6 else stroke.opacity),
                    )
            if abs(baked_opacity - 1.0) > 1e-6:
                kwargs["opacity"] = 1.0
            updated_elements.append(_replace(element, **kwargs) if kwargs else element)
        return updated_elements

    scene.elements = _walk(list(scene.elements))


def _needs_unbaked_native_opacity_effect(animation: AnimationDefinition) -> bool:
    if animation.animation_type != AnimationType.ANIMATE:
        return False
    if animation.target_attribute != "opacity":
        return False

    values = animation.values
    if len(values) == 2 and animation.repeat_count in (None, 1, "1") and not animation.key_times:
        start = _opacity_float(values[0])
        end = _opacity_float(values[-1])
        return (start <= 0.0 and end >= 0.999) or (end <= 0.0 and start >= 0.999)

    if len(values) != 3:
        return False
    if animation.calc_mode == CalcMode.DISCRETE:
        return False
    if animation.key_splines:
        return False
    if animation.key_times and [round(value, 6) for value in animation.key_times] != [0.0, 0.5, 1.0]:
        return False

    start = _opacity_float(values[0])
    peak = _opacity_float(values[1])
    end = _opacity_float(values[2])
    return abs(start - end) <= 1e-6 and start <= 0.0 and peak > start


def _opacity_float(value: str) -> float:
    try:
        opacity = float(value)
    except (TypeError, ValueError):
        return 1.0
    if opacity > 1.0:
        opacity = opacity / 100.0
    return max(0.0, min(1.0, opacity))


# ---------------------------------------------------------------------------
# Sampled center motion composition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SampledCenterMotionComposition:
    replacement_index: int
    consumed_indices: set[int]
    replacement_animation: AnimationDefinition
    updated_indices: dict[int, AnimationDefinition]
    start_center: tuple[float, float]
    element_id: str


def _compose_sampled_center_motions(
    animations: list[AnimationDefinition],
    scene: IRScene,
) -> list[AnimationDefinition]:
    """Compose known stacked transform/motion cases into sampled center paths.

    Some SVG stacks change the shape center in ways PowerPoint cannot infer by
    simply combining independent native effects. For those cases we:

    1. move the base IR element to the authored SVG start center
    2. replace the position-changing fragments with one sampled motion path
    3. keep the editable scale/rotate effect, but suppress its naive companion
       motion because the composed path already includes that center movement
    """
    from svg2ooxml.ir.scene import Group

    alias_map: dict[str, tuple[str, ...]] = {}
    element_map: dict[str, object] = {}
    center_map: dict[str, tuple[float, float]] = {}

    def _walk(elements: list) -> None:
        for el in elements:
            meta = getattr(el, "metadata", None)
            bbox = getattr(el, "bbox", None)
            if isinstance(meta, dict) and bbox is not None:
                element_ids = tuple(
                    dict.fromkeys(
                        eid
                        for eid in meta.get("element_ids", [])
                        if isinstance(eid, str) and eid
                    )
                )
                if element_ids:
                    center = (
                        float(bbox.x + bbox.width / 2.0),
                        float(bbox.y + bbox.height / 2.0),
                    )
                    for element_id in element_ids:
                        alias_map[element_id] = element_ids
                        element_map.setdefault(element_id, el)
                        center_map.setdefault(element_id, center)
            if isinstance(el, Group):
                _walk(getattr(el, "children", []))

    _walk(scene.elements)

    group_map: dict[tuple[Any, ...], list[tuple[int, AnimationDefinition]]] = {}
    for index, animation in enumerate(animations):
        group_key = _sampled_motion_group_key(animation, alias_map)
        group_map.setdefault(group_key, []).append((index, animation))

    compositions: list[_SampledCenterMotionComposition] = []
    for members in group_map.values():
        base_animation = min(members, key=lambda item: item[0])[1]
        element = element_map.get(base_animation.element_id)
        current_center = center_map.get(base_animation.element_id)
        if element is None or current_center is None:
            continue

        composition = _build_sampled_center_motion_composition(
            element=element,
            current_center=current_center,
            members=members,
        )
        if composition is not None:
            compositions.append(composition)

    if not compositions:
        return animations

    center_targets = {
        composition.element_id: composition.start_center
        for composition in compositions
    }
    scene.elements = [
        _translate_element_to_center_target(element, center_targets)
        for element in scene.elements
    ]

    replacements = {
        composition.replacement_index: composition
        for composition in compositions
    }
    updated_indices: dict[int, AnimationDefinition] = {}
    consumed_indices: set[int] = set()
    for composition in compositions:
        updated_indices.update(composition.updated_indices)
        consumed_indices.update(composition.consumed_indices)

    composed: list[AnimationDefinition] = []
    for index, animation in enumerate(animations):
        if index in replacements:
            composed.append(replacements[index].replacement_animation)
        if index in consumed_indices:
            continue
        composed.append(updated_indices.get(index, animation))
    return composed


def _build_sampled_center_motion_composition(
    *,
    element: object,
    current_center: tuple[float, float],
    members: list[tuple[int, AnimationDefinition]],
) -> _SampledCenterMotionComposition | None:
    from dataclasses import replace as _replace

    from svg2ooxml.ir.scene import Group, Image
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Circle, Polygon, Polyline

    if isinstance(element, Circle):
        scale_member = _single_matching_member(
            members,
            lambda anim: (
                anim.animation_type == AnimationType.ANIMATE_TRANSFORM
                and anim.transform_type == TransformType.SCALE
                and _is_simple_linear_two_value_animation(anim)
            ),
        )
        if scale_member is None:
            return None

        numeric_members = {
            anim.target_attribute: (index, anim)
            for index, anim in members
            if _is_simple_linear_numeric_animation(anim)
            and anim.target_attribute in {"x", "y", "cx", "cy"}
        }
        if not numeric_members:
            return None

        matrix = _resolve_affine_matrix(
            [scale_member[1], *(anim for _, anim in numeric_members.values())]
        )
        local_center_x, local_center_y = _inverse_project_affine_point(
            current_center,
            matrix,
        )
        (from_sx, from_sy), (to_sx, to_sy) = _parse_scale_bounds(scale_member[1])

        x0, x1 = _numeric_bounds(numeric_members.get("x"), default=0.0)
        y0, y1 = _numeric_bounds(numeric_members.get("y"), default=0.0)
        cx0, cx1 = _numeric_bounds(numeric_members.get("cx"), default=local_center_x)
        cy0, cy1 = _numeric_bounds(numeric_members.get("cy"), default=local_center_y)

        samples = _sample_progress_values()
        center_points = []
        for progress in samples:
            sx = _lerp(from_sx, to_sx, progress)
            sy = _lerp(from_sy, to_sy, progress)
            tx = _lerp(x0, x1, progress)
            ty = _lerp(y0, y1, progress)
            cx = _lerp(cx0, cx1, progress)
            cy = _lerp(cy0, cy1, progress)
            center_points.append(
                _project_affine_point(
                    (tx + sx * cx, ty + sy * cy),
                    matrix,
                )
            )

        motion_template = min(numeric_members.values(), key=lambda item: item[0])[1]
        replacement_index = min(index for index, _ in numeric_members.values())
        consumed_indices = {index for index, _ in numeric_members.values()}
        updated_scale = _replace(scale_member[1], element_center_px=None)
        updated_indices = {scale_member[0]: updated_scale}
        return _SampledCenterMotionComposition(
            replacement_index=replacement_index,
            consumed_indices=consumed_indices,
            replacement_animation=_build_sampled_motion_replacement(
                template=motion_template,
                points=center_points,
                key_times=samples,
            ),
            updated_indices=updated_indices,
            start_center=center_points[0],
            element_id=motion_template.element_id,
        )

    if isinstance(element, Image):
        scale_member = _single_matching_member(
            members,
            lambda anim: (
                anim.animation_type == AnimationType.ANIMATE_TRANSFORM
                and anim.transform_type == TransformType.SCALE
                and _is_simple_linear_two_value_animation(anim)
            ),
        )
        if scale_member is None:
            return None

        numeric_members = {
            anim.target_attribute: (index, anim)
            for index, anim in members
            if _is_simple_linear_numeric_animation(anim)
            and anim.target_attribute in {"x", "y"}
        }
        if not numeric_members:
            return None

        matrix = _resolve_affine_matrix(
            [scale_member[1], *(anim for _, anim in numeric_members.values())]
        )
        local_bbox = _inverse_project_affine_rect(element.bbox, matrix)
        viewport_rect, content_rect = _image_local_layout(element, local_bbox)
        (from_sx, from_sy), (to_sx, to_sy) = _parse_scale_bounds(scale_member[1])

        x0, x1 = _numeric_bounds(numeric_members.get("x"), default=viewport_rect.x)
        y0, y1 = _numeric_bounds(numeric_members.get("y"), default=viewport_rect.y)
        content_offset_x = float(content_rect.x - viewport_rect.x)
        content_offset_y = float(content_rect.y - viewport_rect.y)
        width = float(content_rect.width)
        height = float(content_rect.height)

        samples = _sample_progress_values()
        center_points = []
        for progress in samples:
            sx = _lerp(from_sx, to_sx, progress)
            sy = _lerp(from_sy, to_sy, progress)
            x = _lerp(x0, x1, progress)
            y = _lerp(y0, y1, progress)
            center_points.append(
                _project_affine_point(
                    (
                        sx * (x + content_offset_x + width / 2.0),
                        sy * (y + content_offset_y + height / 2.0),
                    ),
                    matrix,
                )
            )

        motion_template = min(numeric_members.values(), key=lambda item: item[0])[1]
        replacement_index = min(index for index, _ in numeric_members.values())
        consumed_indices = {index for index, _ in numeric_members.values()}
        updated_scale = _replace(scale_member[1], element_center_px=None)
        updated_indices = {scale_member[0]: updated_scale}
        return _SampledCenterMotionComposition(
            replacement_index=replacement_index,
            consumed_indices=consumed_indices,
            replacement_animation=_build_sampled_motion_replacement(
                template=motion_template,
                points=center_points,
                key_times=samples,
            ),
            updated_indices=updated_indices,
            start_center=center_points[0],
            element_id=motion_template.element_id,
        )

    if isinstance(element, (Group, IRPath, Polyline, Polygon)):
        translate_member = _single_matching_member(
            members,
            lambda anim: (
                anim.animation_type == AnimationType.ANIMATE_TRANSFORM
                and anim.transform_type == TransformType.TRANSLATE
                and len(anim.values) >= 2
                and not anim.key_splines
                and (
                    (
                        anim.calc_mode.value
                        if isinstance(anim.calc_mode, CalcMode)
                        else str(anim.calc_mode).lower()
                    )
                    in {CalcMode.LINEAR.value, CalcMode.PACED.value}
                )
            ),
        )
        rotate_transform_member = None
        if translate_member is not None:
            split_origin = _group_transform_clone_origin(translate_member[1])
            rotate_candidates = [
                (index, anim)
                for index, anim in members
                if anim.animation_type == AnimationType.ANIMATE_TRANSFORM
                and anim.transform_type == TransformType.ROTATE
                and len(anim.values) >= 2
                and (
                    (
                        split_origin is not None
                        and _group_transform_clone_origin(anim) == split_origin
                    )
                    or (
                        split_origin is None
                        and _group_transform_clone_origin(anim) is None
                    )
                )
            ]
            if len(rotate_candidates) == 1:
                rotate_transform_member = rotate_candidates[0]
        if translate_member is not None and rotate_transform_member is not None:
            matrix = _resolve_affine_matrix([translate_member[1], rotate_transform_member[1]])
            local_center = _inverse_project_affine_point(current_center, matrix)
            translation_pairs = [
                _parse_translate_pair(value) for value in translate_member[1].values
            ]
            angles, rotation_center = _parse_rotate_keyframes(rotate_transform_member[1])
            if rotation_center is not None:
                sample_points = {
                    0.0,
                    1.0,
                    *(_sample_progress_values(24)),
                    *(translate_member[1].key_times or []),
                    *(rotate_transform_member[1].key_times or []),
                }
                ordered_samples = sorted(sample_points)
                center_points: list[tuple[float, float]] = []
                for progress in ordered_samples:
                    tx, ty = _interpolate_pair_keyframes(
                        translation_pairs,
                        translate_member[1].key_times,
                        progress,
                    )
                    angle = _interpolate_numeric_keyframes(
                        angles,
                        rotate_transform_member[1].key_times,
                        progress,
                    )
                    rotated_center = _rotate_around_point(
                        local_center,
                        rotation_center,
                        angle,
                    )
                    moved_center = (rotated_center[0] + tx, rotated_center[1] + ty)
                    center_points.append(
                        _project_affine_point(moved_center, matrix)
                    )

                updated_rotate = _replace(
                    rotate_transform_member[1],
                    values=[str(angle) for angle in angles],
                    element_center_px=None,
                )
                return _SampledCenterMotionComposition(
                    replacement_index=translate_member[0],
                    consumed_indices={translate_member[0]},
                    replacement_animation=_build_sampled_motion_replacement(
                        template=translate_member[1],
                        points=center_points,
                        key_times=ordered_samples,
                    ),
                    updated_indices={rotate_transform_member[0]: updated_rotate},
                    start_center=center_points[0],
                    element_id=translate_member[1].element_id,
                )

        motion_member = _single_matching_member(
            members,
            lambda anim: (
                anim.animation_type == AnimationType.ANIMATE_MOTION
                and _is_simple_motion_sampling_candidate(anim)
            ),
        )
        rotate_member = _single_matching_member(
            members,
            lambda anim: (
                anim.animation_type == AnimationType.ANIMATE_TRANSFORM
                and anim.transform_type == TransformType.ROTATE
                and _is_simple_origin_rotate_animation(anim)
            ),
        )
        if motion_member is None or rotate_member is None:
            return None

        matrix = _resolve_affine_matrix([motion_member[1], rotate_member[1]])
        local_center = _inverse_project_affine_point(current_center, matrix)
        motion_points = _parse_sampled_motion_points(motion_member[1].values[0])
        if len(motion_points) < 2:
            return None

        start_angle, end_angle = _parse_rotate_bounds(rotate_member[1])
        samples = _sample_progress_values()
        center_points = []
        for progress in samples:
            motion_point = _sample_polyline_at_fraction(motion_points, progress)
            angle = _lerp(start_angle, end_angle, progress)
            rotated = _rotate_point(
                (local_center[0] + motion_point[0], local_center[1] + motion_point[1]),
                angle,
            )
            center_points.append(_project_affine_point(rotated, matrix))

        return _SampledCenterMotionComposition(
            replacement_index=motion_member[0],
            consumed_indices={motion_member[0]},
            replacement_animation=_build_sampled_motion_replacement(
                template=motion_member[1],
                points=center_points,
                key_times=samples,
            ),
            updated_indices={},
            start_center=center_points[0],
            element_id=motion_member[1].element_id,
        )

    return None
