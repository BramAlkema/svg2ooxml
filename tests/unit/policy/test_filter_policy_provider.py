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


def test_filter_policy_collects_primitive_overrides_from_targets() -> None:
    provider = FilterPolicyProvider()
    target = PolicyTarget("filter")
    payload = {
        "quality": "balanced",
        "targets": {
            "filter": {
                "strategy": "auto",
                "primitives": {
                    "feDiffuseLighting": {
                        "allow_resvg": False,
                        "max_pixels": 2048,
                        "allow_promotion": False,
                        "max_arithmetic_coeff": 0.75,
                        "ignored": "value",
                        "max_offset_distance": 12.5,
                    },
                    "feComponentTransfer": {
                        "max_component_functions": 3,
                        "max_component_table_values": "12",
                    },
                    "feOffset": {
                        "max_offset_distance": "6.5",
                    },
                    "feMerge": {
                        "max_merge_inputs": "4",
                    },
                    "feConvolveMatrix": {
                        "max_convolve_kernel": "9",
                        "max_convolve_order": "16",
                    },
                },
            }
        },
    }

    result = provider.evaluate(target, payload)

    primitives = result.get("primitives")
    assert primitives is not None
    assert primitives["fediffuselighting"]["allow_resvg"] is False
    assert primitives["fediffuselighting"]["max_pixels"] == 2048
    assert primitives["fediffuselighting"]["allow_promotion"] is False
    assert primitives["fediffuselighting"]["max_arithmetic_coeff"] == 0.75
    assert primitives["fediffuselighting"]["max_offset_distance"] == 12.5
    component = primitives["fecomponenttransfer"]
    assert component["max_component_functions"] == 3
    assert component["max_component_table_values"] == 12
    offset = primitives["feoffset"]
    assert offset["max_offset_distance"] == 6.5
    merge = primitives["femerge"]
    assert merge["max_merge_inputs"] == 4
    convolve = primitives["feconvolvematrix"]
    assert convolve["max_convolve_kernel"] == 9
    assert convolve["max_convolve_order"] == 16


def test_filter_policy_collects_dotted_primitive_overrides() -> None:
    provider = FilterPolicyProvider()
    target = PolicyTarget("filter")

    result = provider.evaluate(
        target,
        {
            "quality": "balanced",
            "filter.primitives.feSpecularLighting.allow_resvg": "false",
            "filter.primitives.feSpecularLighting.max_pixels": "8192",
            "filter.primitives.feSpecularLighting.allow_promotion": "on",
            "filter.primitives.feSpecularLighting.max_arithmetic_coeff": "0.5",
            "filter.primitives.feComponentTransfer.max_component_functions": "5",
            "filter.primitives.feComponentTransfer.max_component_table_values": "18",
            "filter.primitives.feOffset.max_offset_distance": "9.75",
            "filter.primitives.feMerge.max_merge_inputs": "6",
            "filter.primitives.feConvolveMatrix.max_convolve_kernel": "13",
            "filter.primitives.feConvolveMatrix.max_convolve_order": "21",
        },
    )

    primitives = result.get("primitives")
    assert primitives is not None
    specular = primitives["fespecularlighting"]
    assert specular["allow_resvg"] is False
    assert specular["max_pixels"] == 8192
    assert specular["allow_promotion"] is True
    assert specular["max_arithmetic_coeff"] == 0.5
    component = primitives["fecomponenttransfer"]
    assert component["max_component_functions"] == 5
    assert component["max_component_table_values"] == 18
    offset = primitives["feoffset"]
    assert offset["max_offset_distance"] == 9.75
    merge = primitives["femerge"]
    assert merge["max_merge_inputs"] == 6
    convolve = primitives["feconvolvematrix"]
    assert convolve["max_convolve_kernel"] == 13
    assert convolve["max_convolve_order"] == 21
