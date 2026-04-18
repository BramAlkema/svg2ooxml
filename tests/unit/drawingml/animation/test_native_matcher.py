from __future__ import annotations

from collections import Counter

from lxml import etree
from tools.visual.w3c_animation_suite import SCENARIOS

from svg2ooxml.core.animation import SMILParser
from svg2ooxml.drawingml.animation.native_matcher import (
    NativeAnimationMatchLevel,
    classify_native_animation,
)
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationTiming,
    AnimationType,
    BeginTrigger,
    BeginTriggerType,
    CalcMode,
    TransformType,
)


def _animation(
    *,
    animation_type: AnimationType = AnimationType.ANIMATE,
    target_attribute: str = "x",
    values: list[str] | None = None,
    calc_mode: CalcMode = CalcMode.LINEAR,
    transform_type: TransformType | None = None,
    timing: AnimationTiming | None = None,
    key_splines: list[list[float]] | None = None,
) -> AnimationDefinition:
    return AnimationDefinition(
        element_id="shape",
        animation_type=animation_type,
        target_attribute=target_attribute,
        values=values or ["0", "1"],
        timing=timing or AnimationTiming(),
        calc_mode=calc_mode,
        transform_type=transform_type,
        key_splines=key_splines,
    )


def test_classifies_simple_opacity_fade_as_exact_native_effect() -> None:
    match = classify_native_animation(
        _animation(target_attribute="opacity", values=["0", "1"])
    )

    assert match.level is NativeAnimationMatchLevel.EXACT_NATIVE
    assert match.primitive == 'p:animEffect[filter="fade"]'
    assert match.reason == "opacity-authored-fade"
    assert not match.mimic_allowed
    assert match.required_evidence_tiers == (
        "schema-valid",
        "loadable",
        "slideshow-verified",
    )


def test_classifies_spline_timing_as_native_mimic() -> None:
    match = classify_native_animation(
        _animation(
            target_attribute="x",
            values=["0", "10"],
            calc_mode=CalcMode.SPLINE,
            key_splines=[[0.42, 0.0, 0.58, 1.0]],
        )
    )

    assert match.level is NativeAnimationMatchLevel.MIMIC_NATIVE
    assert match.primitive == "p:animMotion"
    assert match.reason == "spline-timing-sampled"
    assert match.mimic_allowed
    assert "spline-timing-sampled" in match.limitations


def test_classifies_access_key_trigger_as_unsupported_native() -> None:
    match = classify_native_animation(
        _animation(
            timing=AnimationTiming(
                begin_triggers=[
                    BeginTrigger(
                        trigger_type=BeginTriggerType.ACCESS_KEY,
                        access_key="a",
                    )
                ]
            )
        )
    )

    assert match.level is NativeAnimationMatchLevel.UNSUPPORTED_NATIVE
    assert match.reason == "begin-access-key-unsupported"
    assert not match.mimic_allowed


def test_classifies_display_as_composed_visibility_native() -> None:
    match = classify_native_animation(
        _animation(target_attribute="display", values=["none", "inline"])
    )

    assert match.level is NativeAnimationMatchLevel.COMPOSED_NATIVE
    assert match.primitive == "p:set"
    assert match.strategy == "display-compiled-to-visibility"
    assert match.reason == "display-visibility-compiler"


def test_classifies_skew_transform_as_mimic_native() -> None:
    match = classify_native_animation(
        _animation(
            animation_type=AnimationType.ANIMATE_TRANSFORM,
            target_attribute="transform",
            transform_type=TransformType.SKEWX,
            values=["0", "30"],
        )
    )

    assert match.level is NativeAnimationMatchLevel.MIMIC_NATIVE
    assert match.reason == "transform-skew-no-direct-native"
    assert match.mimic_allowed


def test_native_match_serializes_to_metadata_shape() -> None:
    match = classify_native_animation(
        _animation(target_attribute="width", values=["10", "20"])
    )

    payload = match.to_dict()

    assert payload["level"] == "composed-native"
    assert payload["primitive"] == "p:animScale+p:animMotion"
    assert payload["reason"] == "size-scale-anchor-composed"
    assert payload["required_evidence_tiers"] == [
        "schema-valid",
        "loadable",
        "slideshow-verified",
    ]
    assert payload["limitations"] == []


def test_oracle_backed_match_requires_ui_authored_roundtrip_and_slideshow_evidence() -> None:
    match = classify_native_animation(
        _animation(target_attribute="fill-opacity", values=["0.2", "0.8"])
    )

    assert match.oracle_required is True
    assert match.required_evidence_tiers == (
        "schema-valid",
        "loadable",
        "ui-authored",
        "roundtrip-preserved",
        "slideshow-verified",
    )


def test_w3c_animation_corpus_has_declared_native_match_for_every_definition() -> None:
    total = 0
    levels: Counter[str] = Counter()
    unclassified: list[tuple[str, str, str]] = []

    for name, path in SCENARIOS.items():
        root = etree.fromstring(path.read_text(encoding="utf-8").encode("utf-8"))
        parser = SMILParser()
        for animation in parser.parse_svg_animations(root):
            total += 1
            match = classify_native_animation(animation)
            levels[match.level.value] += 1
            if not match.reason or match.reason.endswith("unclassified"):
                unclassified.append(
                    (
                        name,
                        animation.animation_type.value,
                        animation.target_attribute,
                    )
                )

    assert total == 646
    assert unclassified == []
    assert set(levels) <= {level.value for level in NativeAnimationMatchLevel}
    assert levels["exact-native"] > 0
    assert levels["composed-native"] > 0
    assert levels["mimic-native"] > 0
    assert levels["metadata-only"] > 0
    assert levels["unsupported-native"] > 0
