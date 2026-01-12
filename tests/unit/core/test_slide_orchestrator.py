from __future__ import annotations

from svg2ooxml.core.slide_orchestrator import (
    build_fidelity_tier_variants,
    derive_variants_from_trace,
)


def test_derive_variants_geometry_and_filter() -> None:
    report = {
        "geometry_totals": {"emf": 1},
        "stage_events": [
            {"stage": "filter", "action": "filter_effect", "metadata": {"fallback": "bitmap"}},
        ],
    }
    variants = derive_variants_from_trace(report, enable_split=True)
    names = {variant.name for variant in variants}
    assert "geometry_emf" in names
    assert "filter_raster" in names


def test_derive_variants_mask_emf() -> None:
    report = {
        "stage_events": [
            {"stage": "mask", "action": "processed", "metadata": {"requires_emf": True}},
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
    assert direct["mask"]["fallback_order"] == ("native",)

    bitmap = variants[-1].policy_overrides
    assert bitmap["filter"]["strategy"] == "raster"
