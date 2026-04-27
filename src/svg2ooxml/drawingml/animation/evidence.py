"""Typed evidence tiers for native animation claims and oracle provenance."""

from __future__ import annotations

from enum import StrEnum


class EvidenceTier(StrEnum):
    """Project-wide evidence tiers for animation research and native claims."""

    SCHEMA_VALID = "schema-valid"
    LOADABLE = "loadable"
    ROUNDTRIP_PRESERVED = "roundtrip-preserved"
    SLIDESHOW_VERIFIED = "slideshow-verified"
    UI_AUTHORED = "ui-authored"


def evidence_tiers_for_oracle_verification(verification: str) -> tuple[EvidenceTier, ...]:
    """Map legacy oracle verification labels onto standardized evidence tiers."""
    normalized = verification.strip().lower()
    if normalized == "derived-from-handler":
        return (EvidenceTier.SCHEMA_VALID,)
    if normalized == "oracle-matched":
        return (
            EvidenceTier.SCHEMA_VALID,
            EvidenceTier.LOADABLE,
            EvidenceTier.UI_AUTHORED,
        )
    if normalized == "visually-verified":
        return (
            EvidenceTier.SCHEMA_VALID,
            EvidenceTier.LOADABLE,
            EvidenceTier.SLIDESHOW_VERIFIED,
        )
    return ()


def required_evidence_tiers_for_native_match(
    *,
    level_value: str,
    oracle_required: bool,
    visual_required: bool,
) -> tuple[EvidenceTier, ...]:
    """Return the evidence tiers needed before a native claim is considered closed."""
    if level_value in {"metadata-only", "unsupported-native"}:
        return ()

    tiers: list[EvidenceTier] = [
        EvidenceTier.SCHEMA_VALID,
        EvidenceTier.LOADABLE,
    ]
    if oracle_required:
        tiers.extend(
            [
                EvidenceTier.UI_AUTHORED,
                EvidenceTier.ROUNDTRIP_PRESERVED,
            ]
        )
    if visual_required:
        tiers.append(EvidenceTier.SLIDESHOW_VERIFIED)

    ordered: list[EvidenceTier] = []
    for tier in tiers:
        if tier not in ordered:
            ordered.append(tier)
    return tuple(ordered)
