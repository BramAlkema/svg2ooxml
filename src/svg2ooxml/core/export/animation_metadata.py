"""Animation metadata serialization for export diagnostics."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from svg2ooxml.drawingml.animation.native_matcher import (
    NativeAnimationMatch,
    classify_native_animation,
)
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationScene,
    AnimationSummary,
    AnimationTiming,
    CalcMode,
)


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
        "element_states": {
            element_id: dict(properties)
            for element_id, properties in scene.element_states.items()
        },
    }
