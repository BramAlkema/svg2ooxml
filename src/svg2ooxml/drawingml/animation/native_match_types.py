"""Native animation match result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from svg2ooxml.drawingml.animation.evidence import (
    required_evidence_tiers_for_native_match,
)


class NativeAnimationMatchLevel(StrEnum):
    """Native PowerPoint mapping confidence levels."""

    EXACT_NATIVE = "exact-native"
    COMPOSED_NATIVE = "composed-native"
    EXPAND_NATIVE = "expand-native"
    MIMIC_NATIVE = "mimic-native"
    METADATA_ONLY = "metadata-only"
    UNSUPPORTED_NATIVE = "unsupported-native"


LEVEL_RANK: dict[NativeAnimationMatchLevel, int] = {
    NativeAnimationMatchLevel.EXACT_NATIVE: 0,
    NativeAnimationMatchLevel.COMPOSED_NATIVE: 1,
    NativeAnimationMatchLevel.EXPAND_NATIVE: 2,
    NativeAnimationMatchLevel.MIMIC_NATIVE: 3,
    NativeAnimationMatchLevel.METADATA_ONLY: 4,
    NativeAnimationMatchLevel.UNSUPPORTED_NATIVE: 5,
}


@dataclass(frozen=True, slots=True)
class NativeAnimationMatch:
    """Declared native PowerPoint strategy for one animation definition."""

    level: NativeAnimationMatchLevel
    primitive: str
    strategy: str
    mimic_allowed: bool
    reason: str
    oracle_required: bool = False
    visual_required: bool = False
    confidence: str = "candidate"
    required_evidence_tiers: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to trace/export metadata."""
        return {
            "level": self.level.value,
            "primitive": self.primitive,
            "strategy": self.strategy,
            "mimic_allowed": self.mimic_allowed,
            "reason": self.reason,
            "oracle_required": self.oracle_required,
            "visual_required": self.visual_required,
            "confidence": self.confidence,
            "required_evidence_tiers": list(self.required_evidence_tiers),
            "limitations": list(self.limitations),
        }


@dataclass(slots=True)
class MutableNativeAnimationMatch:
    level: NativeAnimationMatchLevel
    primitive: str
    strategy: str
    mimic_allowed: bool
    reason: str
    oracle_required: bool = False
    visual_required: bool = False
    confidence: str = "candidate"
    limitations: list[str] = field(default_factory=list)

    def apply(
        self,
        level: NativeAnimationMatchLevel,
        reason: str,
        *,
        mimic_allowed: bool = False,
        oracle_required: bool = False,
        visual_required: bool = True,
    ) -> None:
        if reason not in self.limitations:
            self.limitations.append(reason)
        if LEVEL_RANK[level] > LEVEL_RANK[self.level]:
            self.level = level
            self.reason = reason
        self.mimic_allowed = self.mimic_allowed or mimic_allowed
        self.oracle_required = self.oracle_required or oracle_required
        self.visual_required = self.visual_required or visual_required

    def freeze(self) -> NativeAnimationMatch:
        confidence = self.confidence
        if self.level in {
            NativeAnimationMatchLevel.METADATA_ONLY,
            NativeAnimationMatchLevel.UNSUPPORTED_NATIVE,
        }:
            confidence = "declared"
        elif self.oracle_required:
            confidence = "oracle-required"
        required_evidence_tiers = tuple(
            tier.value
            for tier in required_evidence_tiers_for_native_match(
                level_value=self.level.value,
                oracle_required=self.oracle_required,
                visual_required=self.visual_required,
            )
        )
        return NativeAnimationMatch(
            level=self.level,
            primitive=self.primitive,
            strategy=self.strategy,
            mimic_allowed=(
                self.mimic_allowed
                and self.level != NativeAnimationMatchLevel.UNSUPPORTED_NATIVE
            ),
            reason=self.reason,
            oracle_required=self.oracle_required,
            visual_required=self.visual_required,
            confidence=confidence,
            required_evidence_tiers=required_evidence_tiers,
            limitations=tuple(self.limitations),
        )
