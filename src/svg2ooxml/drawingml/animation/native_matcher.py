"""Classify SVG animation IR by editable native PowerPoint strategy."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from svg2ooxml.drawingml.animation.constants import (
    COLOR_ATTRIBUTES,
    DISCRETE_VISIBILITY_ATTRIBUTES,
    FADE_ATTRIBUTES,
)
from svg2ooxml.drawingml.animation.evidence import required_evidence_tiers_for_native_match
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationType,
    BeginTriggerType,
    CalcMode,
    TransformType,
)

__all__ = [
    "NativeAnimationMatch",
    "NativeAnimationMatchLevel",
    "classify_native_animation",
]


class NativeAnimationMatchLevel(str, Enum):
    """Native PowerPoint mapping confidence levels."""

    EXACT_NATIVE = "exact-native"
    COMPOSED_NATIVE = "composed-native"
    EXPAND_NATIVE = "expand-native"
    MIMIC_NATIVE = "mimic-native"
    METADATA_ONLY = "metadata-only"
    UNSUPPORTED_NATIVE = "unsupported-native"


_LEVEL_RANK: dict[NativeAnimationMatchLevel, int] = {
    NativeAnimationMatchLevel.EXACT_NATIVE: 0,
    NativeAnimationMatchLevel.COMPOSED_NATIVE: 1,
    NativeAnimationMatchLevel.EXPAND_NATIVE: 2,
    NativeAnimationMatchLevel.MIMIC_NATIVE: 3,
    NativeAnimationMatchLevel.METADATA_ONLY: 4,
    NativeAnimationMatchLevel.UNSUPPORTED_NATIVE: 5,
}

_POSITION_ATTRIBUTES = {"x", "y", "cx", "cy", "ppt_x", "ppt_y"}
_SIZE_ATTRIBUTES = {"width", "height", "w", "h", "rx", "ry", "ppt_w", "ppt_h"}
_LINE_ENDPOINT_ATTRIBUTES = {"x1", "y1", "x2", "y2"}
_SHAPE_MORPH_ATTRIBUTES = {"d", "points"}
_TEXT_STYLE_ATTRIBUTES = {
    "font-family",
    "font-size",
    "font-style",
    "font-weight",
    "text-anchor",
    "textLength",
    "letter-spacing",
}
_STROKE_STYLE_ATTRIBUTES = {
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
}
_REFERENCE_ATTRIBUTES = {
    "class",
    "xlink:href",
    "href",
    "in",
    "clipPathUnits",
    "preserveAspectRatio",
    "spreadMethod",
    "viewBox",
    "fill-rule",
    "paint-order",
}
_GRADIENT_PAINT_ATTRIBUTES = {"stop-color", "stop-opacity"}
_FILTER_PAINT_ATTRIBUTES = {"flood-color", "lighting-color"}


@dataclass(frozen=True, slots=True)
class NativeAnimationMatch:
    """Declared native PowerPoint strategy for one animation definition."""

    level: NativeAnimationMatchLevel
    primitive: str
    strategy: str
    mimic_allowed: bool
    reason: str
    oracle_required: bool = False
    visual_required: bool = False
    confidence: str = "candidate"
    required_evidence_tiers: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to trace/export metadata."""
        return {
            "level": self.level.value,
            "primitive": self.primitive,
            "strategy": self.strategy,
            "mimic_allowed": self.mimic_allowed,
            "reason": self.reason,
            "oracle_required": self.oracle_required,
            "visual_required": self.visual_required,
            "confidence": self.confidence,
            "required_evidence_tiers": list(self.required_evidence_tiers),
            "limitations": list(self.limitations),
        }


@dataclass(slots=True)
class _MutableMatch:
    level: NativeAnimationMatchLevel
    primitive: str
    strategy: str
    mimic_allowed: bool
    reason: str
    oracle_required: bool = False
    visual_required: bool = False
    confidence: str = "candidate"
    limitations: list[str] = field(default_factory=list)

    def apply(
        self,
        level: NativeAnimationMatchLevel,
        reason: str,
        *,
        mimic_allowed: bool = False,
        oracle_required: bool = False,
        visual_required: bool = True,
    ) -> None:
        if reason not in self.limitations:
            self.limitations.append(reason)
        if _LEVEL_RANK[level] > _LEVEL_RANK[self.level]:
            self.level = level
            self.reason = reason
        self.mimic_allowed = self.mimic_allowed or mimic_allowed
        self.oracle_required = self.oracle_required or oracle_required
        self.visual_required = self.visual_required or visual_required

    def freeze(self) -> NativeAnimationMatch:
        confidence = self.confidence
        if self.level in {
            NativeAnimationMatchLevel.METADATA_ONLY,
            NativeAnimationMatchLevel.UNSUPPORTED_NATIVE,
        }:
            confidence = "declared"
        elif self.oracle_required:
            confidence = "oracle-required"
        required_evidence_tiers = tuple(
            tier.value
            for tier in required_evidence_tiers_for_native_match(
                level_value=self.level.value,
                oracle_required=self.oracle_required,
                visual_required=self.visual_required,
            )
        )
        return NativeAnimationMatch(
            level=self.level,
            primitive=self.primitive,
            strategy=self.strategy,
            mimic_allowed=(
                self.mimic_allowed
                and self.level != NativeAnimationMatchLevel.UNSUPPORTED_NATIVE
            ),
            reason=self.reason,
            oracle_required=self.oracle_required,
            visual_required=self.visual_required,
            confidence=confidence,
            required_evidence_tiers=required_evidence_tiers,
            limitations=tuple(self.limitations),
        )


def classify_native_animation(animation: AnimationDefinition) -> NativeAnimationMatch:
    """Return the best declared native PowerPoint match for an animation."""
    match = _classify_core(animation)
    _apply_value_form_constraints(match, animation)
    _apply_interpolation_constraints(match, animation)
    _apply_additive_accumulate_constraints(match, animation)
    _apply_timing_constraints(match, animation)
    return match.freeze()


def _classify_core(animation: AnimationDefinition) -> _MutableMatch:
    if animation.animation_type == AnimationType.ANIMATE_MOTION:
        return _MutableMatch(
            level=NativeAnimationMatchLevel.EXACT_NATIVE,
            primitive="p:animMotion",
            strategy="motion-path",
            mimic_allowed=False,
            reason="animate-motion-path",
            visual_required=True,
        )

    if animation.animation_type == AnimationType.ANIMATE_TRANSFORM:
        return _classify_transform(animation)

    if animation.animation_type == AnimationType.ANIMATE_COLOR:
        return _classify_color(animation, reason_prefix="animate-color")

    if animation.animation_type == AnimationType.SET:
        return _classify_set(animation)

    if animation.animation_type == AnimationType.ANIMATE:
        return _classify_animate(animation)

    return _MutableMatch(
        level=NativeAnimationMatchLevel.UNSUPPORTED_NATIVE,
        primitive="none",
        strategy="unsupported-animation-type",
        mimic_allowed=False,
        reason="unsupported-animation-type",
    )


def _classify_transform(animation: AnimationDefinition) -> _MutableMatch:
    transform_type = animation.transform_type
    if transform_type == TransformType.TRANSLATE:
        return _MutableMatch(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "p:animMotion",
            "transform-translate-motion",
            False,
            "transform-translate-motion",
            visual_required=True,
        )
    if transform_type == TransformType.SCALE:
        return _MutableMatch(
            NativeAnimationMatchLevel.COMPOSED_NATIVE,
            "p:animScale+p:animMotion",
            "transform-scale-with-origin-compensation",
            False,
            "transform-scale-composed",
            visual_required=True,
        )
    if transform_type == TransformType.ROTATE:
        return _MutableMatch(
            NativeAnimationMatchLevel.COMPOSED_NATIVE,
            "p:animRot+p:animMotion",
            "transform-rotate-with-center-compensation",
            False,
            "transform-rotate-composed",
            visual_required=True,
        )
    if transform_type in {TransformType.SKEWX, TransformType.SKEWY}:
        return _MutableMatch(
            NativeAnimationMatchLevel.MIMIC_NATIVE,
            "static-variants",
            "transform-skew-mimic",
            True,
            "transform-skew-no-direct-native",
            visual_required=True,
        )
    if transform_type == TransformType.MATRIX:
        return _MutableMatch(
            NativeAnimationMatchLevel.METADATA_ONLY,
            "decomposition-required",
            "transform-matrix-decompose",
            False,
            "transform-matrix-needs-decomposition",
            oracle_required=True,
            visual_required=True,
        )
    return _MutableMatch(
        NativeAnimationMatchLevel.METADATA_ONLY,
        "none",
        "transform-type-missing",
        False,
        "transform-type-missing",
    )


def _classify_animate(animation: AnimationDefinition) -> _MutableMatch:
    attr = animation.target_attribute

    if attr in FADE_ATTRIBUTES:
        if attr == "opacity" and _is_simple_authored_fade(animation):
            return _MutableMatch(
                NativeAnimationMatchLevel.EXACT_NATIVE,
                'p:animEffect[filter="fade"]',
                "authored-fade-effect",
                False,
                "opacity-authored-fade",
                visual_required=True,
            )
        return _MutableMatch(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "p:anim",
            "opacity-property-animation",
            False,
            "opacity-property-native",
            oracle_required=attr in {"fill-opacity", "stroke-opacity"},
            visual_required=True,
        )

    if attr in COLOR_ATTRIBUTES or attr == "color":
        return _classify_color(animation, reason_prefix="animate-color-attribute")

    if attr in _GRADIENT_PAINT_ATTRIBUTES | _FILTER_PAINT_ATTRIBUTES:
        return _classify_color(animation, reason_prefix="animate-paint-attribute")

    if attr == "display":
        return _MutableMatch(
            NativeAnimationMatchLevel.COMPOSED_NATIVE,
            "p:set",
            "display-compiled-to-visibility",
            False,
            "display-visibility-compiler",
            visual_required=True,
        )

    if attr in DISCRETE_VISIBILITY_ATTRIBUTES:
        return _MutableMatch(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "p:set",
            "visibility-set",
            False,
            "visibility-set-native",
            visual_required=True,
        )

    if attr in _POSITION_ATTRIBUTES:
        return _MutableMatch(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "p:animMotion",
            "numeric-position-motion",
            False,
            "numeric-position-motion",
            visual_required=True,
        )

    if attr in _SIZE_ATTRIBUTES:
        return _MutableMatch(
            NativeAnimationMatchLevel.COMPOSED_NATIVE,
            "p:animScale+p:animMotion",
            "size-scale-with-anchor-motion",
            False,
            "size-scale-anchor-composed",
            visual_required=True,
        )

    if attr == "r":
        return _MutableMatch(
            NativeAnimationMatchLevel.COMPOSED_NATIVE,
            "p:animScale",
            "radius-uniform-scale",
            False,
            "radius-scale-composed",
            oracle_required=True,
            visual_required=True,
        )

    if attr in _LINE_ENDPOINT_ATTRIBUTES:
        return _MutableMatch(
            NativeAnimationMatchLevel.COMPOSED_NATIVE,
            "p:animMotion+p:animScale",
            "line-endpoint-composition",
            False,
            "line-endpoint-composed",
            visual_required=True,
        )

    if attr == "stroke-width":
        return _MutableMatch(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "p:anim",
            "stroke-weight-animation",
            False,
            "stroke-weight-native",
            visual_required=True,
        )

    if attr in {"stroke-dashoffset", "stroke-dasharray"}:
        return _MutableMatch(
            NativeAnimationMatchLevel.MIMIC_NATIVE,
            "p:animEffect",
            "stroke-dash-wipe-mimic",
            True,
            "stroke-dash-reveal-mimic",
            visual_required=True,
        )

    if attr in _SHAPE_MORPH_ATTRIBUTES:
        return _MutableMatch(
            NativeAnimationMatchLevel.MIMIC_NATIVE,
            "static-variants",
            "shape-morph-mimic",
            True,
            "shape-morph-no-direct-native",
            visual_required=True,
        )

    if attr in _TEXT_STYLE_ATTRIBUTES:
        return _MutableMatch(
            NativeAnimationMatchLevel.METADATA_ONLY,
            "text-property",
            "text-attribute-target-unverified",
            False,
            "text-attribute-target-unverified",
            oracle_required=True,
            visual_required=True,
        )

    if attr in _STROKE_STYLE_ATTRIBUTES:
        return _MutableMatch(
            NativeAnimationMatchLevel.METADATA_ONLY,
            "line-style-property",
            "stroke-style-target-unverified",
            False,
            "stroke-style-target-unverified",
            oracle_required=True,
            visual_required=True,
        )

    if attr in _REFERENCE_ATTRIBUTES:
        return _MutableMatch(
            NativeAnimationMatchLevel.UNSUPPORTED_NATIVE,
            "none",
            "reference-or-rendering-attribute",
            False,
            f"{attr}-no-runtime-native-target",
        )

    return _MutableMatch(
        NativeAnimationMatchLevel.METADATA_ONLY,
        "p:anim",
        "generic-property-target-unverified",
        False,
        "generic-property-target-unverified",
        oracle_required=True,
        visual_required=True,
    )


def _classify_color(
    animation: AnimationDefinition,
    *,
    reason_prefix: str,
) -> _MutableMatch:
    attr = animation.target_attribute
    if attr in _GRADIENT_PAINT_ATTRIBUTES:
        return _MutableMatch(
            NativeAnimationMatchLevel.MIMIC_NATIVE,
            "gradient-stop-property",
            "gradient-stop-animation-mimic",
            True,
            f"{reason_prefix}-gradient-stop-mimic",
            oracle_required=True,
            visual_required=True,
        )
    if attr in _FILTER_PAINT_ATTRIBUTES:
        return _MutableMatch(
            NativeAnimationMatchLevel.MIMIC_NATIVE,
            "effect-property",
            "filter-color-animation-mimic",
            True,
            f"{reason_prefix}-filter-color-mimic",
            oracle_required=True,
            visual_required=True,
        )
    return _MutableMatch(
        NativeAnimationMatchLevel.EXACT_NATIVE,
        "p:animClr",
        "flat-color-animation",
        False,
        f"{reason_prefix}-flat-color-native",
        visual_required=True,
    )


def _classify_set(animation: AnimationDefinition) -> _MutableMatch:
    attr = animation.target_attribute

    if attr == "display":
        return _MutableMatch(
            NativeAnimationMatchLevel.COMPOSED_NATIVE,
            "p:set",
            "display-compiled-to-visibility",
            False,
            "set-display-visibility-compiler",
            visual_required=True,
        )

    if attr in DISCRETE_VISIBILITY_ATTRIBUTES:
        return _MutableMatch(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "p:set",
            "visibility-set",
            False,
            "set-visibility-native",
            visual_required=True,
        )

    if attr in COLOR_ATTRIBUTES or attr == "color":
        return _MutableMatch(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "p:set",
            "color-set",
            False,
            "set-color-native",
            visual_required=True,
        )

    if attr in _POSITION_ATTRIBUTES | _SIZE_ATTRIBUTES | {"stroke-width"}:
        return _MutableMatch(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "p:set",
            "numeric-property-set",
            False,
            "set-numeric-native",
            oracle_required=True,
            visual_required=True,
        )

    if attr in {"stroke-dashoffset", "stroke-dasharray"}:
        return _MutableMatch(
            NativeAnimationMatchLevel.MIMIC_NATIVE,
            "p:animEffect",
            "stroke-dash-set-mimic",
            True,
            "set-stroke-dash-mimic",
            visual_required=True,
        )

    if attr in _TEXT_STYLE_ATTRIBUTES | _STROKE_STYLE_ATTRIBUTES:
        return _MutableMatch(
            NativeAnimationMatchLevel.METADATA_ONLY,
            "p:set",
            "categorical-property-set-unverified",
            False,
            "set-categorical-target-unverified",
            oracle_required=True,
            visual_required=True,
        )

    if attr in _REFERENCE_ATTRIBUTES:
        return _MutableMatch(
            NativeAnimationMatchLevel.UNSUPPORTED_NATIVE,
            "none",
            "reference-or-rendering-attribute",
            False,
            f"set-{attr}-no-runtime-native-target",
        )

    return _MutableMatch(
        NativeAnimationMatchLevel.METADATA_ONLY,
        "p:set",
        "generic-set-target-unverified",
        False,
        "set-generic-target-unverified",
        oracle_required=True,
        visual_required=True,
    )


def _apply_value_form_constraints(
    match: _MutableMatch,
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


def _apply_interpolation_constraints(
    match: _MutableMatch,
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


def _apply_additive_accumulate_constraints(
    match: _MutableMatch,
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


def _apply_timing_constraints(
    match: _MutableMatch,
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


def _is_simple_authored_fade(animation: AnimationDefinition) -> bool:
    if animation.target_attribute != "opacity":
        return False
    if len(animation.values) != 2 or animation.key_times:
        return False
    if animation.repeat_count not in (None, 1, "1"):
        return False

    start = _opacity_float(animation.values[0])
    end = _opacity_float(animation.values[-1])
    return (start <= 0.0 and end >= 0.999) or (end <= 0.0 and start >= 0.999)


def _opacity_float(value: str) -> float:
    try:
        opacity = float(value)
    except (TypeError, ValueError):
        return 1.0
    if opacity > 1.0:
        opacity = opacity / 100.0
    return max(0.0, min(1.0, opacity))
