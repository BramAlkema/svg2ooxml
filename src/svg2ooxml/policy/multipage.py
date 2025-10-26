"""Policy helpers that expose multi-slide orchestration toggles."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MultipagePolicy:
    """Feature flags controlling slide orchestration behaviour."""

    split_fallback_variants: bool = False


def extract_multipage_policy(policy_context) -> MultipagePolicy:
    """Build a MultipagePolicy from the policy context if available."""

    selections = getattr(policy_context, "selections", {}) or {}
    multipage_cfg = selections.get("multipage", {})

    return MultipagePolicy(
        split_fallback_variants=bool(multipage_cfg.get("split_fallback_variants")),
    )

