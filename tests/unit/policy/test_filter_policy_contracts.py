from __future__ import annotations

from svg2ooxml.policy.providers.filter import FilterPolicyProvider
from svg2ooxml.policy.targets import PolicyTarget

ALLOWED_STRATEGIES = {"auto", "native", "native-if-neutral", "vector", "emf", "raster", "resvg"}
ALLOWED_GLOW_STRATEGIES = {"inherit", "source", "flood", "style"}
ALLOWED_BLUR_STRATEGIES = {"soft_edge", "blur", "outer_shadow", "inner_shadow"}
ALLOWED_TELEMETRY_LEVELS = {"off", "summary", "detailed"}


def _assert_non_negative(value: int | float | None, label: str) -> None:
    assert value is not None, f"{label} should be set"
    assert value >= 0, f"{label} should be non-negative"


def test_filter_policy_contracts_for_quality_presets() -> None:
    provider = FilterPolicyProvider()
    target = PolicyTarget("filter")

    for quality in ("high", "balanced", "low", "compatibility"):
        payload = provider.evaluate(target, {"quality": quality})

        assert payload.get("quality") == quality
        assert payload.get("strategy") in ALLOWED_STRATEGIES
        assert payload.get("preferred_glow_strategy") in ALLOWED_GLOW_STRATEGIES
        assert payload.get("blur_strategy") in ALLOWED_BLUR_STRATEGIES
        assert payload.get("telemetry_level") in ALLOWED_TELEMETRY_LEVELS

        assert isinstance(payload.get("allow_anisotropic_native"), bool)
        assert isinstance(payload.get("prefer_emf_blend_modes"), bool)
        assert isinstance(payload.get("native_blur"), bool)
        assert isinstance(payload.get("native_shadow"), bool)
        assert isinstance(payload.get("approximation_allowed"), bool)
        assert isinstance(payload.get("prefer_rasterization"), bool)
        assert isinstance(payload.get("enable_telemetry"), bool)

        _assert_non_negative(payload.get("max_bitmap_stddev"), "max_bitmap_stddev")
        _assert_non_negative(payload.get("max_shadow_distance"), "max_shadow_distance")
        _assert_non_negative(payload.get("max_convolve_kernel"), "max_convolve_kernel")
        _assert_non_negative(payload.get("max_glow_radius"), "max_glow_radius")
        _assert_non_negative(payload.get("max_glow_alpha"), "max_glow_alpha")
        _assert_non_negative(payload.get("max_filter_primitives"), "max_filter_primitives")
        _assert_non_negative(payload.get("max_filter_complexity"), "max_filter_complexity")

        if not payload.get("enable_telemetry"):
            assert payload.get("telemetry_level") == "off"
