"""Tests for filter policy provider glow heuristics."""

from __future__ import annotations

from svg2ooxml.policy.providers.filter import FilterPolicyProvider
from svg2ooxml.policy.targets import PolicyTarget


def test_filter_policy_provider_emits_glow_thresholds() -> None:
    provider = FilterPolicyProvider()
    target = PolicyTarget("filter")
    result = provider.evaluate(target, {"quality": "balanced"})

    assert "max_glow_radius" in result
    assert result["max_glow_radius"] == 8.0
    assert "max_glow_alpha" in result
    assert result["max_glow_alpha"] == 0.75
    assert result["preferred_glow_strategy"] == "inherit"


def test_filter_policy_respects_overrides() -> None:
    provider = FilterPolicyProvider()
    target = PolicyTarget("filter")
    payload = {
        "quality": "low",
        "max_glow_radius": 3,
        "max_glow_alpha": 0.4,
        "preferred_glow_strategy": "flood",
    }

    result = provider.evaluate(target, payload)

    assert result["max_glow_radius"] == 3.0
    assert result["max_glow_alpha"] == 0.4
    assert result["preferred_glow_strategy"] == "flood"
