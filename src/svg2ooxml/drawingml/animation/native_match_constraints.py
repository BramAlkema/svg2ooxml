"""Constraint downgrades for native animation classification."""

from __future__ import annotations

from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationType,
    BeginTriggerType,
    CalcMode,
)

from .native_match_types import MutableNativeAnimationMatch, NativeAnimationMatchLevel


def apply_native_match_constraints(
    match: MutableNativeAnimationMatch,
    animation: AnimationDefinition,
) -> None:
    apply_value_form_constraints(match, animation)
    apply_interpolation_constraints(match, animation)
    apply_additive_accumulate_constraints(match, animation)
    apply_timing_constraints(match, animation)


def apply_value_form_constraints(
    match: MutableNativeAnimationMatch,
    animation: AnimationDefinition,
) -> None:
    if animation.animation_type == AnimationType.SET:
        return

    if animation.by_value is not None and len(animation.values) <= 1:
        match.apply(
            NativeAnimationMatchLevel.METADATA_ONLY,
            "by-only-needs-underlying-target-value",
            oracle_required=True,
        )

    if animation.to_value is not None and len(animation.values) <= 1:
        match.apply(
            NativeAnimationMatchLevel.METADATA_ONLY,
            "to-only-needs-underlying-target-value",
            oracle_required=True,
        )


def apply_interpolation_constraints(
    match: MutableNativeAnimationMatch,
    animation: AnimationDefinition,
) -> None:
    if animation.key_splines or animation.calc_mode == CalcMode.SPLINE:
        match.apply(
            NativeAnimationMatchLevel.MIMIC_NATIVE,
            "spline-timing-sampled",
            mimic_allowed=True,
            visual_required=True,
        )

    if animation.key_points:
        match.apply(
            NativeAnimationMatchLevel.MIMIC_NATIVE,
            "motion-keypoints-retimed",
            mimic_allowed=True,
            visual_required=True,
        )

    if animation.calc_mode == CalcMode.PACED:
        match.apply(
            NativeAnimationMatchLevel.EXPAND_NATIVE,
            "paced-timing-expanded",
            visual_required=True,
        )

    if animation.calc_mode == CalcMode.DISCRETE and animation.animation_type != AnimationType.SET:
        match.apply(
            NativeAnimationMatchLevel.EXPAND_NATIVE,
            "discrete-timing-segmented",
            visual_required=True,
        )

    if (
        animation.key_times is not None
        and match.primitive in {"p:animClr", "p:animScale+p:animMotion", "p:animMotion"}
        and animation.calc_mode not in {CalcMode.SPLINE, CalcMode.PACED}
    ):
        match.apply(
            NativeAnimationMatchLevel.EXPAND_NATIVE,
            "key-times-require-segmentation",
            visual_required=True,
        )


def apply_additive_accumulate_constraints(
    match: MutableNativeAnimationMatch,
    animation: AnimationDefinition,
) -> None:
    additive = (animation.additive or "replace").lower()
    accumulate = (animation.accumulate or "none").lower()

    if additive == "sum":
        if animation.is_color_animation():
            match.apply(
                NativeAnimationMatchLevel.UNSUPPORTED_NATIVE,
                "additive-color-unsupported",
            )
        else:
            match.apply(
                NativeAnimationMatchLevel.EXPAND_NATIVE,
                "additive-sum-needs-composition",
                oracle_required=True,
                visual_required=True,
            )

    if accumulate == "sum":
        if animation.repeat_count == "indefinite":
            match.apply(
                NativeAnimationMatchLevel.UNSUPPORTED_NATIVE,
                "accumulate-sum-indefinite-unsupported",
            )
        else:
            match.apply(
                NativeAnimationMatchLevel.EXPAND_NATIVE,
                "accumulate-sum-expanded",
                visual_required=True,
            )


def apply_timing_constraints(
    match: MutableNativeAnimationMatch,
    animation: AnimationDefinition,
) -> None:
    timing = animation.timing

    for trigger in timing.begin_triggers or []:
        trigger_type = trigger.trigger_type
        if trigger_type in {BeginTriggerType.TIME_OFFSET, BeginTriggerType.CLICK}:
            continue
        if trigger_type in {BeginTriggerType.ELEMENT_BEGIN, BeginTriggerType.ELEMENT_END}:
            if not trigger.target_element_id:
                match.apply(
                    NativeAnimationMatchLevel.METADATA_ONLY,
                    "begin-element-trigger-target-missing",
                    oracle_required=True,
                )
            else:
                match.apply(
                    NativeAnimationMatchLevel.EXACT_NATIVE,
                    "begin-element-trigger-native",
                    oracle_required=True,
                    visual_required=True,
                )
            continue
        if trigger_type == BeginTriggerType.INDEFINITE:
            match.apply(
                NativeAnimationMatchLevel.METADATA_ONLY,
                "begin-indefinite-needs-trigger-rewrite",
                oracle_required=True,
            )
            continue
        if trigger_type == BeginTriggerType.ELEMENT_REPEAT:
            match.apply(
                NativeAnimationMatchLevel.METADATA_ONLY,
                "begin-repeat-event-not-wired",
                mimic_allowed=True,
                oracle_required=True,
            )
            continue
        if trigger_type == BeginTriggerType.ACCESS_KEY:
            match.apply(
                NativeAnimationMatchLevel.UNSUPPORTED_NATIVE,
                "begin-access-key-unsupported",
            )
            continue
        if trigger_type == BeginTriggerType.WALLCLOCK:
            match.apply(
                NativeAnimationMatchLevel.UNSUPPORTED_NATIVE,
                "begin-wallclock-unsupported",
            )
            continue
        if trigger_type == BeginTriggerType.EVENT:
            match.apply(
                NativeAnimationMatchLevel.UNSUPPORTED_NATIVE,
                "begin-dom-event-unsupported",
            )

    for trigger in timing.end_triggers or []:
        trigger_type = trigger.trigger_type
        if trigger_type in {
            BeginTriggerType.TIME_OFFSET,
            BeginTriggerType.CLICK,
            BeginTriggerType.ELEMENT_BEGIN,
            BeginTriggerType.ELEMENT_END,
        }:
            match.apply(
                NativeAnimationMatchLevel.EXACT_NATIVE,
                "end-condition-native",
                oracle_required=True,
                visual_required=True,
            )
            continue
        match.apply(
            NativeAnimationMatchLevel.UNSUPPORTED_NATIVE,
            f"end-{trigger_type.value}-unsupported",
        )

    if timing.repeat_duration is not None:
        match.apply(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "repeat-duration-native",
            oracle_required=True,
            visual_required=True,
        )

    if animation.restart is not None:
        match.apply(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "restart-native",
            oracle_required=True,
            visual_required=True,
        )

    if animation.min_ms is not None or animation.max_ms is not None:
        match.apply(
            NativeAnimationMatchLevel.METADATA_ONLY,
            "min-max-duration-not-wired",
            oracle_required=True,
            visual_required=True,
        )
