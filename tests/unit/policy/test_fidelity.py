from __future__ import annotations

import pytest

from svg2ooxml.policy.fidelity import (
    DEFAULT_FIDELITY_POLICY,
    FidelityDecision,
    FidelityTier,
    resolve_fidelity,
)


def test_fidelity_policy_is_available_from_policy_package() -> None:
    from svg2ooxml.policy import FidelityPolicy, FidelityTier

    assert FidelityPolicy().resolve_tier(FidelityTier.EMF).name == "emf"


def test_fidelity_policy_owns_tier_order_and_overrides() -> None:
    assert DEFAULT_FIDELITY_POLICY.tier_names() == (
        "direct",
        "mimic",
        "emf",
        "bitmap",
    )

    direct = DEFAULT_FIDELITY_POLICY.resolve_tier(FidelityTier.DIRECT)
    assert direct.policy_overrides["filter"]["strategy"] == "native"
    assert direct.policy_overrides["mask"]["fallback_order"] == ("native",)

    bitmap = DEFAULT_FIDELITY_POLICY.resolve_tier("bitmap")
    assert bitmap.policy_overrides["filter"]["strategy"] == "raster"
    assert bitmap.policy_overrides["geometry"]["allow_bitmap_fallback"] is True


def test_fidelity_policy_returns_isolated_override_clones() -> None:
    first = DEFAULT_FIDELITY_POLICY.policy_overrides_for("emf")
    second = DEFAULT_FIDELITY_POLICY.policy_overrides_for("emf")

    first["filter"]["strategy"] = "raster"

    assert second["filter"]["strategy"] == "emf"
    assert DEFAULT_FIDELITY_POLICY.resolve_tier("emf").policy_overrides["filter"]["strategy"] == "emf"


def test_fidelity_policy_public_tiers_do_not_expose_global_defaults() -> None:
    resolved = DEFAULT_FIDELITY_POLICY.resolve_tier("emf")
    listed = DEFAULT_FIDELITY_POLICY.tiers()[2]

    resolved.policy_overrides["filter"]["strategy"] = "raster"
    listed.policy_overrides["filter"]["strategy"] = "raster"

    assert DEFAULT_FIDELITY_POLICY.resolve_tier("emf").policy_overrides["filter"]["strategy"] == "emf"
    assert DEFAULT_FIDELITY_POLICY.policy_overrides_for("emf")["filter"]["strategy"] == "emf"


def test_fidelity_policy_rejects_unknown_tier() -> None:
    with pytest.raises(ValueError, match="Unknown fidelity tier"):
        DEFAULT_FIDELITY_POLICY.resolve_tier("unknown")


def test_resolve_fidelity_honours_explicit_tier_context() -> None:
    assert resolve_fidelity("style") is FidelityDecision.NATIVE
    assert (
        resolve_fidelity("style", context={"fidelity_tier": "emf"})
        is FidelityDecision.VECTOR_BAKE
    )
    assert (
        resolve_fidelity("style", context={"fidelity_tier": "bitmap"})
        is FidelityDecision.RASTER_BAKE
    )
    assert (
        resolve_fidelity("style", context={"fidelity_tier": "unknown"})
        is FidelityDecision.NATIVE
    )
