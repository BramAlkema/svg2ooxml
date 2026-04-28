"""WordArt warp classification utilities ported from svg2pptx."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from svg2ooxml.ir.text_path import PathPoint, TextPathFrame

from .wordart_features import (
    compute_features,
    count_extrema,
    count_sign_changes,
    count_zero_crossings,
    determine_orientation,
    linear_regression,
    pairwise_slopes,
    path_is_closed,
    summarize_features,
)
from .wordart_features import (
    count_corners as count_path_corners,
)
from .wordart_presets import (
    classify_arch_family,
    classify_bulge_family,
    classify_circle,
    classify_linear,
    classify_polygonal,
    classify_wave_family,
    collect_candidates,
    select_best_candidate,
    side_orientation,
)
from .wordart_types import PathFeatures, PresetCandidate, WordArtClassificationResult


@dataclass(frozen=True)
class _CompatPoint:
    x: float
    y: float


def classify_text_path_warp(
    text_path: TextPathFrame,
    path_points: Sequence[PathPoint],
    *,
    path_data: str | None = None,
) -> WordArtClassificationResult | None:
    """Classify a sampled text path into a DrawingML warp preset."""

    if not path_points or len(path_points) < 4:
        return None

    features = compute_features(path_points, path_data)

    if (
        features.curvature_sign_changes == 0
        and features.peak_count == 0
        and features.trough_count == 0
        and features.y_range <= 1e-3
    ):
        return WordArtClassificationResult(
            preset="textPlain",
            confidence=0.9,
            parameters={"slope": features.slope},
            reason="Detected flat baseline",
            features=summarize_features(features),
        )

    if (
        features.zero_crossings >= 2
        and features.peak_count >= 1
        and features.trough_count >= 1
        and not features.is_closed
    ):
        return WordArtClassificationResult(
            preset="textWave1",
            confidence=0.85,
            parameters={"amplitude": features.amplitude},
            reason="Baseline exhibits wave-like oscillation",
            features=summarize_features(features),
        )

    best = select_best_candidate(features, collect_candidates(text_path, features))
    if not best or best.confidence < 0.40:
        return None

    return WordArtClassificationResult(
        preset=best.preset,
        confidence=min(best.confidence, 0.99),
        parameters=best.parameters,
        reason=best.reason,
        features=summarize_features(features),
    )


_Candidate = PresetCandidate
_classify_arch_family = classify_arch_family
_classify_bulge_family = classify_bulge_family
_classify_circle = classify_circle
_classify_linear = classify_linear
_classify_polygonal = classify_polygonal
_classify_wave_family = classify_wave_family
_compute_features = compute_features
_count_extrema = count_extrema
_count_sign_changes = count_sign_changes
_count_zero_crossings = count_zero_crossings
_determine_orientation = determine_orientation
_linear_regression = linear_regression
_pairwise_slopes = pairwise_slopes
_path_is_closed = path_is_closed
_side_orientation = side_orientation
_summarise_features = summarize_features


def _count_corners(xs: Sequence[float], ys: Sequence[float]) -> int:
    return count_path_corners([_CompatPoint(x, y) for x, y in zip(xs, ys, strict=True)])


__all__ = [
    "PathFeatures",
    "WordArtClassificationResult",
    "classify_text_path_warp",
    "_Candidate",
    "_classify_arch_family",
    "_classify_bulge_family",
    "_classify_circle",
    "_classify_linear",
    "_classify_polygonal",
    "_classify_wave_family",
    "_compute_features",
    "_count_corners",
    "_count_extrema",
    "_count_sign_changes",
    "_count_zero_crossings",
    "_determine_orientation",
    "_linear_regression",
    "_pairwise_slopes",
    "_path_is_closed",
    "_side_orientation",
    "_summarise_features",
]
