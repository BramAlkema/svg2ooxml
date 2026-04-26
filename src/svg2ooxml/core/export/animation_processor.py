"""Animation serialization helpers, enrichment, and sampled center motion composition."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import replace
from math import isfinite
from typing import Any

from svg2ooxml.core.export.motion_geometry import _infer_element_heading_deg
from svg2ooxml.core.export.sampled_center_motion import (
    _compose_sampled_center_motions,
    _is_polyline_segment_fade_animation,
    _is_simple_line_endpoint_animation,
    _is_simple_motion_sampling_candidate,
    _is_simple_origin_rotate_animation,
    _parse_rotate_bounds,
    _sampled_motion_group_key,
    _simple_position_axis,
    _timing_group_key,
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

__all__ = [
    "_build_animation_metadata",
    "_compose_sampled_center_motions",
    "_enrich_animations_with_element_centers",
    "_expand_deterministic_repeat_triggers",
    "_is_polyline_segment_fade_animation",
    "_is_simple_line_endpoint_animation",
    "_is_simple_motion_sampling_candidate",
    "_is_simple_origin_rotate_animation",
    "_lower_safe_group_transform_targets_with_animated_descendants",
    "_parse_rotate_bounds",
    "_prepare_scene_for_native_opacity_effects",
    "_sampled_motion_group_key",
    "_simple_position_axis",
    "_timing_group_key",
]

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
