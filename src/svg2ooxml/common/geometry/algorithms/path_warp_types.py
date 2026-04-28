"""Shared types for path-to-WordArt warp fitting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from svg2ooxml.ir.text_path import PathPoint

EXCELLENT_THRESHOLD = 0.95
GOOD_THRESHOLD = 0.80
FAIR_THRESHOLD = 0.60


@dataclass
class WarpFitResult:
    """Result of path fitting to a parametric warp family."""

    preset_type: str
    confidence: float
    error_metric: float
    parameters: dict[str, Any]
    fit_quality: str


class TextPathPositioner(Protocol):
    def sample_path_for_text(
        self,
        path_data: str,
        num_samples: int | None = None,
    ) -> list[PathPoint]: ...


def classify_fit_quality(confidence: float) -> str:
    """Classify fit quality based on confidence score."""

    if confidence >= EXCELLENT_THRESHOLD:
        return "excellent"
    if confidence >= GOOD_THRESHOLD:
        return "good"
    if confidence >= FAIR_THRESHOLD:
        return "fair"
    return "poor"


def no_fit_result(reason: str) -> WarpFitResult:
    return WarpFitResult(
        preset_type="none",
        confidence=0.0,
        error_metric=float("inf"),
        parameters={"reason": reason},
        fit_quality="poor",
    )


def poor_fit_result(preset_type: str) -> WarpFitResult:
    return WarpFitResult(
        preset_type=preset_type,
        confidence=0.0,
        error_metric=float("inf"),
        parameters={},
        fit_quality="poor",
    )


__all__ = [
    "EXCELLENT_THRESHOLD",
    "FAIR_THRESHOLD",
    "GOOD_THRESHOLD",
    "TextPathPositioner",
    "WarpFitResult",
    "classify_fit_quality",
    "no_fit_result",
    "poor_fit_result",
]
