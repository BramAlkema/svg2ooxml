"""Fidelity policies for native, vector, EMF, and bitmap trade-offs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar


class FidelityDecision(Enum):
    """Enumerator describing how a feature should be rendered."""

    NATIVE = "native"
    VECTOR_BAKE = "vector_bake"
    RASTER_BAKE = "raster_bake"


class FidelityTier(Enum):
    """Named fidelity tiers used by exporters and visual tooling."""

    DIRECT = "direct"
    MIMIC = "mimic"
    EMF = "emf"
    BITMAP = "bitmap"


PolicyOverrideBucket = dict[str, object]
PolicyOverrides = dict[str, PolicyOverrideBucket]


@dataclass(frozen=True, slots=True)
class FidelityTierPolicy:
    """Typed policy bundle for one fidelity tier."""

    tier: FidelityTier
    title_suffix: str
    policy_overrides: PolicyOverrides

    @property
    def name(self) -> str:
        return self.tier.value

    def clone_overrides(self) -> PolicyOverrides:
        """Return mutable policy overrides for one conversion request."""

        return deepcopy(self.policy_overrides)

    def clone(self) -> FidelityTierPolicy:
        """Return an isolated mutable copy of this policy bundle."""

        return FidelityTierPolicy(
            tier=self.tier,
            title_suffix=self.title_suffix,
            policy_overrides=self.clone_overrides(),
        )


class FidelityPolicy:
    """Central source for fidelity tier policy bundles."""

    _TIERS: ClassVar[tuple[FidelityTierPolicy, ...]] = (
        FidelityTierPolicy(
            tier=FidelityTier.DIRECT,
            title_suffix=" (Direct)",
            policy_overrides={
                "geometry": {
                    "allow_emf_fallback": False,
                    "allow_bitmap_fallback": False,
                    "simplify_paths": False,
                },
                "filter": {
                    "strategy": "native",
                    "approximation_allowed": False,
                    "prefer_rasterization": False,
                },
                "mask": {
                    "allow_vector_mask": True,
                    "force_emf": False,
                    "force_raster": False,
                    "fallback_order": ("native",),
                },
                "clip": {"fallback_order": ("native",)},
            },
        ),
        FidelityTierPolicy(
            tier=FidelityTier.MIMIC,
            title_suffix=" (Mimic)",
            policy_overrides={
                "geometry": {
                    "allow_emf_fallback": False,
                    "allow_bitmap_fallback": False,
                    "simplify_paths": True,
                },
                "filter": {
                    "strategy": "native",
                    "approximation_allowed": True,
                    "prefer_rasterization": False,
                },
                "mask": {
                    "allow_vector_mask": True,
                    "force_emf": False,
                    "force_raster": False,
                    "fallback_order": ("native", "mimic"),
                },
                "clip": {"fallback_order": ("native", "mimic")},
            },
        ),
        FidelityTierPolicy(
            tier=FidelityTier.EMF,
            title_suffix=" (EMF)",
            policy_overrides={
                "geometry": {
                    "allow_emf_fallback": True,
                    "allow_bitmap_fallback": False,
                },
                "filter": {
                    "strategy": "emf",
                    "approximation_allowed": False,
                    "prefer_rasterization": False,
                },
                "mask": {
                    "allow_vector_mask": True,
                    "force_emf": False,
                    "force_raster": False,
                    "fallback_order": ("native", "mimic", "emf"),
                },
                "clip": {"fallback_order": ("native", "mimic", "emf")},
            },
        ),
        FidelityTierPolicy(
            tier=FidelityTier.BITMAP,
            title_suffix=" (Bitmap)",
            policy_overrides={
                "geometry": {
                    "allow_emf_fallback": True,
                    "allow_bitmap_fallback": True,
                },
                "filter": {
                    "strategy": "raster",
                    "approximation_allowed": False,
                    "prefer_rasterization": True,
                },
                "mask": {
                    "allow_vector_mask": True,
                    "force_emf": False,
                    "force_raster": False,
                    "fallback_order": ("native", "mimic", "emf", "raster"),
                },
                "clip": {"fallback_order": ("native", "mimic", "emf", "raster")},
            },
        ),
    )

    def tiers(self) -> tuple[FidelityTierPolicy, ...]:
        """Return all fidelity tiers in presentation order."""

        return tuple(policy.clone() for policy in self._TIERS)

    def tier_names(self) -> tuple[str, ...]:
        """Return accepted fidelity tier names in presentation order."""

        return tuple(policy.name for policy in self._TIERS)

    def resolve_tier(self, tier: FidelityTier | str) -> FidelityTierPolicy:
        """Resolve a tier enum or name to a policy bundle."""

        target = tier.value if isinstance(tier, FidelityTier) else tier.strip().lower()
        for policy in self._TIERS:
            if policy.name == target:
                return policy.clone()
        raise ValueError(f"Unknown fidelity tier: {tier!r}")

    def policy_overrides_for(self, tier: FidelityTier | str) -> PolicyOverrides:
        """Return mutable overrides for one tier."""

        return self.resolve_tier(tier).clone_overrides()


DEFAULT_FIDELITY_POLICY = FidelityPolicy()


def resolve_fidelity(
    feature: str,
    *,
    node: Any | None = None,
    context: dict[str, Any] | None = None,
) -> FidelityDecision:
    """Return the desired fidelity strategy for a feature.

    The current resolver keeps native rendering as the default, but honours an
    optional ``fidelity_tier`` context when callers explicitly request broad
    vector or raster fallback behavior.
    """

    del feature, node
    tier_name = (context or {}).get("fidelity_tier")
    if isinstance(tier_name, str):
        try:
            tier = DEFAULT_FIDELITY_POLICY.resolve_tier(tier_name).tier
        except ValueError:
            tier = None
        if tier is FidelityTier.BITMAP:
            return FidelityDecision.RASTER_BAKE
        if tier is FidelityTier.EMF:
            return FidelityDecision.VECTOR_BAKE
    return FidelityDecision.NATIVE


__all__ = [
    "DEFAULT_FIDELITY_POLICY",
    "FidelityDecision",
    "FidelityPolicy",
    "FidelityTier",
    "FidelityTierPolicy",
    "PolicyOverrideBucket",
    "PolicyOverrides",
    "resolve_fidelity",
]
