"""Shared data types for WordArt path classification."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PathFeatures:
    """Derived metrics describing sampled baseline geometry."""

    is_closed: bool
    point_count: int
    x_range: float
    y_range: float
    slope: float
    intercept: float
    slope_degrees: float
    curvature_sign_changes: int
    peak_count: int
    trough_count: int
    corner_count: int
    zero_crossings: int
    arc_command_count: int
    line_command_count: int
    command_counts: Counter[str]
    orientation: str
    amplitude: float
    mean_y: float
    std_y: float
    x_variance: float
    y_variance: float

    def aspect_ratio(self) -> float:
        return self.x_range / max(self.y_range, 1e-6)


@dataclass
class WordArtClassificationResult:
    """Classification outcome for WordArt detection."""

    preset: str
    confidence: float
    parameters: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    features: dict[str, Any] | None = None


@dataclass(frozen=True)
class PresetCandidate:
    preset: str
    confidence: float
    parameters: dict[str, Any]
    reason: str


__all__ = [
    "PathFeatures",
    "PresetCandidate",
    "WordArtClassificationResult",
]
