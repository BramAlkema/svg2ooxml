"""Simplified font metadata structures for IR text rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FontStrategy(Enum):
    EMBEDDED = "embedded"
    SYSTEM = "system"
    PATH = "path"
    FALLBACK = "fallback"


class FontAvailability(Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
    EMBEDDED = "embedded"
    SYSTEM_FALLBACK = "system_fallback"


@dataclass(frozen=True)
class FontMetrics:
    ascent: float = 0.8
    descent: float = 0.2
    line_height: float = 1.2
    x_height: float = 0.5
    cap_height: float = 0.7

    @property
    def total_height(self) -> float:
        return self.ascent + self.descent


@dataclass(frozen=True)
class FontMetadata:
    family: str
    weight: int = 400
    style: str = "normal"
    size_pt: float = 12.0
    strategy: FontStrategy = FontStrategy.SYSTEM
    availability: FontAvailability = FontAvailability.UNKNOWN
    metrics: FontMetrics | None = None
    embedding_required: bool = False
    embedding_confidence: float = 0.0
    fallback_chain: list[str] = field(default_factory=lambda: ["Arial", "sans-serif"])
    variation_settings: dict[str, Any] | None = None
    feature_settings: list[str] | None = None
    kerning: bool = True
    variant: str = "normal"
    stretch: str = "normal"

    def __post_init__(self) -> None:
        if not self.family.strip():
            raise ValueError("font family cannot be empty")
        if not (100 <= self.weight <= 900):
            raise ValueError("font weight must be between 100 and 900")
        if self.size_pt <= 0:
            raise ValueError("font size must be positive")

    @property
    def is_bold(self) -> bool:
        return self.weight >= 700

    @property
    def is_italic(self) -> bool:
        return self.style.lower() in {"italic", "oblique"}

    @property
    def effective_metrics(self) -> FontMetrics:
        return self.metrics or FontMetrics()


__all__ = [
    "FontStrategy",
    "FontAvailability",
    "FontMetrics",
    "FontMetadata",
]
