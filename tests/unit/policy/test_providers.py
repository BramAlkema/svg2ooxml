"""Tests covering policy providers."""

import pytest

from svg2ooxml.policy.providers.animation import AnimationPolicyProvider
from svg2ooxml.policy.providers.image import ImagePolicyProvider
from svg2ooxml.policy.providers.mask import MaskPolicyProvider
from svg2ooxml.policy.providers.path import PathPolicyProvider
from svg2ooxml.policy.providers.text import TextPolicyProvider
from svg2ooxml.policy.targets import PolicyTarget


def test_image_policy_quality_variants() -> None:
    provider = ImagePolicyProvider()
    target = PolicyTarget("image")

    high = provider.evaluate(target, {"quality": "high"})
    low = provider.evaluate(target, {"quality": "low"})

    assert high["colorspace_normalization"] == "perceptual"
    assert high["prefer_vector"] is True
    assert high["max_downscale"] == pytest.approx(0.75)
    assert low["colorspace_normalization"] == "skip"
    assert low["prefer_vector"] is False
    assert low["max_inline_size_kib"] == 2048


def test_text_policy_respects_quality() -> None:
    provider = TextPolicyProvider()
    target = PolicyTarget("text")

    balanced = provider.evaluate(target, {"quality": "balanced"})
    conservative = provider.evaluate(target, {"quality": "low"})

    assert balanced["fallback"]["missing_font_behavior"] == "outline"
    assert balanced["allow_effects"] is True
    assert balanced["decision"].max_runs == 2048

    assert conservative["fallback"]["missing_font_behavior"] == "fallback_family"
    assert conservative["allow_effects"] is False
    assert conservative["decision"].wordart.enable_detection is False


def test_text_policy_allows_overrides() -> None:
    provider = TextPolicyProvider()
    target = PolicyTarget("text")

    payload = provider.evaluate(
        target,
        {"quality": "high", "text.embed_fonts": False, "text.wordart.enable": False},
    )

    decision = payload["decision"]

    assert decision.embedding.embed_when_available is False
    assert decision.wordart.enable_detection is False
    assert payload["embedding"]["embed_when_available"] is False


def test_path_policy_limits_adjust_with_quality() -> None:
    provider = PathPolicyProvider()
    target = PolicyTarget("geometry")

    high = provider.evaluate(target, {"quality": "high"})
    low = provider.evaluate(target, {"quality": "low"})

    assert high["max_segments"] > low["max_segments"]


def test_mask_policy_balanced_defaults() -> None:
    provider = MaskPolicyProvider()
    target = PolicyTarget("mask")

    balanced = provider.evaluate(target, {"quality": "balanced"})
    low = provider.evaluate(target, {"quality": "low"})

    assert balanced["fallback_order"][:3] == ("native", "mimic", "emf")
    assert balanced["allow_vector_mask"] is True
    assert low["allow_vector_mask"] is False
    assert low["fallback_order"] == ("emf", "raster")
    assert balanced["force_emf"] is False
    assert balanced["force_raster"] is False


def test_animation_policy_defaults() -> None:
    provider = AnimationPolicyProvider()
    target = PolicyTarget("animation")

    balanced = provider.evaluate(target, {"quality": "balanced"})
    assert balanced["allow_native_splines"] is True
    assert balanced["fallback_mode"] == "native"
    assert balanced["max_spline_error"] == pytest.approx(0.35)


def test_animation_policy_allows_overrides() -> None:
    provider = AnimationPolicyProvider()
    target = PolicyTarget("animation")

    payload = provider.evaluate(
        target,
        {
            "quality": "balanced",
            "animation_allow_native_splines": "false",
            "animation_fallback_mode": "raster",
            "animation_max_spline_error": "0.02",
        },
    )

    assert payload["allow_native_splines"] is False
    assert payload["fallback_mode"] == "raster"
    assert payload["max_spline_error"] == pytest.approx(0.02)
