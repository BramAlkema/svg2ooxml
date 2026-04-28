"""Animation oracle public types and constants."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from svg2ooxml.drawingml.animation.constants import SVG2_ANIMATION_NS
from svg2ooxml.drawingml.animation.evidence import (
    EvidenceTier,
    evidence_tiers_for_oracle_verification,
)

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_BUILD_MODE_ATTR = f"{{{SVG2_ANIMATION_NS}}}bldMode"


class OracleSlotError(KeyError):
    """Raised when a requested oracle slot cannot be resolved."""


@dataclass(frozen=True, slots=True)
class PresetSlot:
    """Metadata describing a single oracle slot."""

    name: str
    path: Path
    preset_class: str
    preset_id: int | None
    preset_subtype: int | None
    bld_mode: str
    family_signature: str
    content_tokens: tuple[str, ...]
    behavior_tokens: tuple[str, ...]
    smil_patterns: tuple[str, ...]
    source: str
    verification: str
    notes: str = ""

    @property
    def evidence_tiers(self) -> tuple[EvidenceTier, ...]:
        return evidence_tiers_for_oracle_verification(self.verification)


@dataclass(frozen=True, slots=True)
class BehaviorFragment:
    """A behavior fragment to inject into a compound slot."""

    name: str
    tokens: Mapping[str, Any] = field(default_factory=dict)


def _default_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "assets" / "animation_oracle"


__all__ = [
    "NS_A",
    "BehaviorFragment",
    "OracleSlotError",
    "PresetSlot",
    "_BUILD_MODE_ATTR",
    "_default_root",
]
