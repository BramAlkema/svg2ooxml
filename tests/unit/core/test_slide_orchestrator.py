from __future__ import annotations

from svg2ooxml.core.pptx_exporter import SvgPageSource
from svg2ooxml.core.slide_orchestrator import (
    build_fidelity_tier_variants,
    derive_variants_from_trace,
    expand_page_with_variants,
    resolve_fidelity_tier_variant,
)


def test_derive_variants_geometry_and_filter() -> None:
    report = {
        "geometry_totals": {"emf": 1},
        "stage_events": [
            {
                "stage": "filter",
                "action": "filter_effect",
                "metadata": {"fallback": "bitmap"},
            },
        ],
    }
    variants = derive_variants_from_trace(report, enable_split=True)
    names = {variant.name for variant in variants}
    assert "geometry_emf" in names
    assert "filter_raster" in names


def test_derive_variants_accepts_nested_filter_metadata() -> None:
    report = {
        "stage_events": [
            {
                "stage": "filter",
                "action": "filter_effect",
                "metadata": {"metadata": {"fallback": "emf"}},
            },
            {"stage": 10, "metadata": {"fallback": "bitmap"}},
        ],
    }

    variants = derive_variants_from_trace(report, enable_split=True)

    assert [variant.name for variant in variants] == ["filter_emf"]


def test_derive_variants_mask_emf() -> None:
    report = {
        "stage_events": [
            {
                "stage": "mask",
                "action": "processed",
                "metadata": {"requires_emf": True},
            },
        ],
    }
    variants = derive_variants_from_trace(report, enable_split=True)
    assert any(variant.name == "mask_emf" for variant in variants)


def test_build_fidelity_tier_variants() -> None:
    variants = build_fidelity_tier_variants()

    names = [variant.name for variant in variants]
    assert names == ["direct", "mimic", "emf", "bitmap"]

    direct = variants[0].policy_overrides
    assert direct["geometry"]["allow_emf_fallback"] is False
    assert direct["filter"]["strategy"] == "native"
    assert direct["filter"]["approximation_allowed"] is False
    assert direct["mask"]["fallback_order"] == ("native",)

    mimic = variants[1].policy_overrides
    assert mimic["filter"]["strategy"] == "native"
    assert mimic["filter"]["approximation_allowed"] is True

    bitmap = variants[-1].policy_overrides
    assert bitmap["filter"]["strategy"] == "raster"
    assert bitmap["filter"]["approximation_allowed"] is False


def test_resolve_fidelity_tier_variant_returns_expected_policy() -> None:
    variant = resolve_fidelity_tier_variant("emf")

    assert variant.name == "emf"
    assert variant.policy_overrides["filter"]["strategy"] == "emf"
    assert variant.policy_overrides["filter"]["approximation_allowed"] is False


def test_expand_page_with_variants_keeps_variant_overrides_isolated() -> None:
    page = SvgPageSource(
        svg_text="<svg xmlns='http://www.w3.org/2000/svg'/>",
        title="Sample",
        name="sample",
        metadata={
            "policy_overrides": {
                "filter": {
                    "enable_effect_dag": True,
                    "enable_native_color_transforms": True,
                    "enable_blip_effect_enrichment": True,
                }
            }
        },
    )

    variants = expand_page_with_variants(page, build_fidelity_tier_variants())
    by_name = {
        variant.metadata["variant"]["type"]: variant.metadata["policy_overrides"][
            "filter"
        ]
        for variant in variants
    }

    assert by_name["direct"]["strategy"] == "native"
    assert by_name["direct"]["approximation_allowed"] is False
    assert by_name["mimic"]["strategy"] == "native"
    assert by_name["mimic"]["approximation_allowed"] is True
    assert by_name["emf"]["strategy"] == "emf"
    assert by_name["bitmap"]["strategy"] == "raster"
    assert page.metadata == {
        "policy_overrides": {
            "filter": {
                "enable_effect_dag": True,
                "enable_native_color_transforms": True,
                "enable_blip_effect_enrichment": True,
            }
        }
    }
