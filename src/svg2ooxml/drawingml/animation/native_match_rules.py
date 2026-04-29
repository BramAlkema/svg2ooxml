"""Base native animation classification rules."""

from __future__ import annotations

from svg2ooxml.common.conversions.opacity import parse_authored_opacity
from svg2ooxml.drawingml.animation.constants import (
    COLOR_ATTRIBUTES,
    DISCRETE_VISIBILITY_ATTRIBUTES,
    FADE_ATTRIBUTES,
)
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationType,
    TransformType,
)

from .native_match_types import MutableNativeAnimationMatch, NativeAnimationMatchLevel

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


def classify_native_match_core(animation: AnimationDefinition) -> MutableNativeAnimationMatch:
    if animation.animation_type == AnimationType.ANIMATE_MOTION:
        return MutableNativeAnimationMatch(
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

    return MutableNativeAnimationMatch(
        level=NativeAnimationMatchLevel.UNSUPPORTED_NATIVE,
        primitive="none",
        strategy="unsupported-animation-type",
        mimic_allowed=False,
        reason="unsupported-animation-type",
    )


def _classify_transform(animation: AnimationDefinition) -> MutableNativeAnimationMatch:
    transform_type = animation.transform_type
    if transform_type == TransformType.TRANSLATE:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "p:animMotion",
            "transform-translate-motion",
            False,
            "transform-translate-motion",
            visual_required=True,
        )
    if transform_type == TransformType.SCALE:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.COMPOSED_NATIVE,
            "p:animScale+p:animMotion",
            "transform-scale-with-origin-compensation",
            False,
            "transform-scale-composed",
            visual_required=True,
        )
    if transform_type == TransformType.ROTATE:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.COMPOSED_NATIVE,
            "p:animRot+p:animMotion",
            "transform-rotate-with-center-compensation",
            False,
            "transform-rotate-composed",
            visual_required=True,
        )
    if transform_type in {TransformType.SKEWX, TransformType.SKEWY}:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.MIMIC_NATIVE,
            "static-variants",
            "transform-skew-mimic",
            True,
            "transform-skew-no-direct-native",
            visual_required=True,
        )
    if transform_type == TransformType.MATRIX:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.METADATA_ONLY,
            "decomposition-required",
            "transform-matrix-decompose",
            False,
            "transform-matrix-needs-decomposition",
            oracle_required=True,
            visual_required=True,
        )
    return MutableNativeAnimationMatch(
        NativeAnimationMatchLevel.METADATA_ONLY,
        "none",
        "transform-type-missing",
        False,
        "transform-type-missing",
    )


def _classify_animate(animation: AnimationDefinition) -> MutableNativeAnimationMatch:
    attr = animation.target_attribute

    if attr in FADE_ATTRIBUTES:
        if attr == "opacity" and _is_simple_authored_fade(animation):
            return MutableNativeAnimationMatch(
                NativeAnimationMatchLevel.EXACT_NATIVE,
                'p:animEffect[filter="fade"]',
                "authored-fade-effect",
                False,
                "opacity-authored-fade",
                visual_required=True,
            )
        return MutableNativeAnimationMatch(
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
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.COMPOSED_NATIVE,
            "p:set",
            "display-compiled-to-visibility",
            False,
            "display-visibility-compiler",
            visual_required=True,
        )

    if attr in DISCRETE_VISIBILITY_ATTRIBUTES:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "p:set",
            "visibility-set",
            False,
            "visibility-set-native",
            visual_required=True,
        )

    if attr in _POSITION_ATTRIBUTES:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "p:animMotion",
            "numeric-position-motion",
            False,
            "numeric-position-motion",
            visual_required=True,
        )

    if attr in _SIZE_ATTRIBUTES:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.COMPOSED_NATIVE,
            "p:animScale+p:animMotion",
            "size-scale-with-anchor-motion",
            False,
            "size-scale-anchor-composed",
            visual_required=True,
        )

    if attr == "r":
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.COMPOSED_NATIVE,
            "p:animScale",
            "radius-uniform-scale",
            False,
            "radius-scale-composed",
            oracle_required=True,
            visual_required=True,
        )

    if attr in _LINE_ENDPOINT_ATTRIBUTES:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.COMPOSED_NATIVE,
            "p:animMotion+p:animScale",
            "line-endpoint-composition",
            False,
            "line-endpoint-composed",
            visual_required=True,
        )

    if attr == "stroke-width":
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "p:anim",
            "stroke-weight-animation",
            False,
            "stroke-weight-native",
            visual_required=True,
        )

    if attr in {"stroke-dashoffset", "stroke-dasharray"}:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.MIMIC_NATIVE,
            "p:animEffect",
            "stroke-dash-wipe-mimic",
            True,
            "stroke-dash-reveal-mimic",
            visual_required=True,
        )

    if attr in _SHAPE_MORPH_ATTRIBUTES:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.MIMIC_NATIVE,
            "static-variants",
            "shape-morph-mimic",
            True,
            "shape-morph-no-direct-native",
            visual_required=True,
        )

    if attr in _TEXT_STYLE_ATTRIBUTES:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.METADATA_ONLY,
            "text-property",
            "text-attribute-target-unverified",
            False,
            "text-attribute-target-unverified",
            oracle_required=True,
            visual_required=True,
        )

    if attr in _STROKE_STYLE_ATTRIBUTES:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.METADATA_ONLY,
            "line-style-property",
            "stroke-style-target-unverified",
            False,
            "stroke-style-target-unverified",
            oracle_required=True,
            visual_required=True,
        )

    if attr in _REFERENCE_ATTRIBUTES:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.UNSUPPORTED_NATIVE,
            "none",
            "reference-or-rendering-attribute",
            False,
            f"{attr}-no-runtime-native-target",
        )

    return MutableNativeAnimationMatch(
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
) -> MutableNativeAnimationMatch:
    attr = animation.target_attribute
    if attr in _GRADIENT_PAINT_ATTRIBUTES:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.MIMIC_NATIVE,
            "gradient-stop-property",
            "gradient-stop-animation-mimic",
            True,
            f"{reason_prefix}-gradient-stop-mimic",
            oracle_required=True,
            visual_required=True,
        )
    if attr in _FILTER_PAINT_ATTRIBUTES:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.MIMIC_NATIVE,
            "effect-property",
            "filter-color-animation-mimic",
            True,
            f"{reason_prefix}-filter-color-mimic",
            oracle_required=True,
            visual_required=True,
        )
    return MutableNativeAnimationMatch(
        NativeAnimationMatchLevel.EXACT_NATIVE,
        "p:animClr",
        "flat-color-animation",
        False,
        f"{reason_prefix}-flat-color-native",
        visual_required=True,
    )


def _classify_set(animation: AnimationDefinition) -> MutableNativeAnimationMatch:
    attr = animation.target_attribute

    if attr == "display":
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.COMPOSED_NATIVE,
            "p:set",
            "display-compiled-to-visibility",
            False,
            "set-display-visibility-compiler",
            visual_required=True,
        )

    if attr in DISCRETE_VISIBILITY_ATTRIBUTES:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "p:set",
            "visibility-set",
            False,
            "set-visibility-native",
            visual_required=True,
        )

    if attr in COLOR_ATTRIBUTES or attr == "color":
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "p:set",
            "color-set",
            False,
            "set-color-native",
            visual_required=True,
        )

    if attr in _POSITION_ATTRIBUTES | _SIZE_ATTRIBUTES | {"stroke-width"}:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.EXACT_NATIVE,
            "p:set",
            "numeric-property-set",
            False,
            "set-numeric-native",
            oracle_required=True,
            visual_required=True,
        )

    if attr in {"stroke-dashoffset", "stroke-dasharray"}:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.MIMIC_NATIVE,
            "p:animEffect",
            "stroke-dash-set-mimic",
            True,
            "set-stroke-dash-mimic",
            visual_required=True,
        )

    if attr in _TEXT_STYLE_ATTRIBUTES | _STROKE_STYLE_ATTRIBUTES:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.METADATA_ONLY,
            "p:set",
            "categorical-property-set-unverified",
            False,
            "set-categorical-target-unverified",
            oracle_required=True,
            visual_required=True,
        )

    if attr in _REFERENCE_ATTRIBUTES:
        return MutableNativeAnimationMatch(
            NativeAnimationMatchLevel.UNSUPPORTED_NATIVE,
            "none",
            "reference-or-rendering-attribute",
            False,
            f"set-{attr}-no-runtime-native-target",
        )

    return MutableNativeAnimationMatch(
        NativeAnimationMatchLevel.METADATA_ONLY,
        "p:set",
        "generic-set-target-unverified",
        False,
        "set-generic-target-unverified",
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
    return parse_authored_opacity(value)
