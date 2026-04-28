"""Preset scoring helpers for WordArt path classification."""

from __future__ import annotations

import math
from collections.abc import Sequence

from svg2ooxml.ir.text_path import TextPathFrame, TextPathSide

from .wordart_types import PathFeatures, PresetCandidate


def side_orientation(text_path: TextPathFrame) -> int:
    """Return +1 or -1 based on the text path side."""

    side = getattr(text_path, "side", None)
    if isinstance(side, TextPathSide):
        return 1 if side == TextPathSide.LEFT else -1
    if isinstance(side, str):
        normalized = side.lower()
        if normalized in {"left", "top"}:
            return 1
        if normalized in {"right", "bottom"}:
            return -1
    return 1


def collect_candidates(
    text_path: TextPathFrame, features: PathFeatures
) -> list[PresetCandidate]:
    candidates: list[PresetCandidate] = []
    candidates.extend(classify_circle(features))
    candidates.extend(classify_arch_family(text_path, features))
    candidates.extend(classify_wave_family(text_path, features))
    candidates.extend(classify_bulge_family(text_path, features))
    candidates.extend(classify_linear(text_path, features))
    candidates.extend(classify_polygonal(text_path, features))
    return candidates


def select_best_candidate(
    features: PathFeatures,
    candidates: Sequence[PresetCandidate],
) -> PresetCandidate | None:
    wave_candidates = [
        candidate for candidate in candidates if candidate.preset == "textWave1"
    ]
    if features.zero_crossings >= 2 and not features.is_closed and wave_candidates:
        return max(
            wave_candidates, key=lambda candidate: candidate.confidence, default=None
        )
    return max(candidates, key=lambda candidate: candidate.confidence, default=None)


def classify_circle(features: PathFeatures) -> list[PresetCandidate]:
    if not features.is_closed or features.point_count < 16:
        return []

    ratio = features.aspect_ratio()
    ratio_conf = max(0.0, 1.0 - abs(1.0 - ratio))
    variance_conf = max(0.0, 1.0 - (features.std_y / max(features.y_range, 1e-6)))
    confidence = min(0.95, (ratio_conf + variance_conf) / 2)
    if confidence < 0.55:
        return []

    return [
        PresetCandidate(
            preset="textCircle",
            confidence=confidence,
            parameters={},
            reason="Closed near-circular baseline",
        )
    ]


def classify_arch_family(
    text_path: TextPathFrame, features: PathFeatures
) -> list[PresetCandidate]:
    if (
        features.curvature_sign_changes > 2
        or features.y_range < 1e-3
        or features.peak_count > 1
        or features.trough_count > 1
        or features.zero_crossings > 2
    ):
        return []

    orientation = side_orientation(text_path)
    amplitude = features.amplitude

    arch_ratio = amplitude / max(features.y_range, 1e-6)
    curvature_consistency = max(0.0, 1.0 - features.curvature_sign_changes * 0.3)
    confidence = min(0.95, (arch_ratio + curvature_consistency) / 2)
    if confidence < 0.4:
        return []

    return [
        PresetCandidate(
            preset="textArchUp" if orientation > 0 else "textArchDown",
            confidence=confidence,
            parameters={"amplitude": amplitude * orientation},
            reason="Arch-like baseline with consistent curvature",
        )
    ]


def classify_wave_family(
    text_path: TextPathFrame, features: PathFeatures
) -> list[PresetCandidate]:
    if features.curvature_sign_changes < 2:
        return []

    is_horizontal = abs(features.slope) < 0.05
    if not is_horizontal:
        return []

    amplitude = features.amplitude
    if features.zero_crossings >= 2 and not features.is_closed:
        confidence = 0.85
    else:
        confidence = min(0.95, amplitude / max(features.y_range, 1e-6))
    if confidence < 0.55:
        return []

    return [
        PresetCandidate(
            preset="textWave1",
            confidence=confidence,
            parameters={"amplitude": amplitude},
            reason="Wave-like oscillation with multiple zero crossings",
        )
    ]


def classify_bulge_family(
    text_path: TextPathFrame, features: PathFeatures
) -> list[PresetCandidate]:
    if features.curvature_sign_changes > 2 or features.point_count < 12:
        return []

    orientation = side_orientation(text_path)
    amplitude = features.amplitude

    confidence = min(0.9, max(0.0, amplitude / max(features.y_range, 1e-6)))
    if confidence < 0.55:
        return []

    return [
        PresetCandidate(
            preset="textInflateTop" if orientation > 0 else "textInflateBottom",
            confidence=confidence,
            parameters={"amplitude": amplitude * orientation},
            reason="Bulge-like baseline with smooth curvature",
        )
    ]


def classify_linear(
    text_path: TextPathFrame, features: PathFeatures
) -> list[PresetCandidate]:
    if features.curvature_sign_changes > 0 or abs(features.slope) < 0.01:
        return []

    angle = math.degrees(math.atan(features.slope))
    confidence = min(
        0.9, max(0.0, 1.0 - abs(features.std_y) / max(features.y_range, 1e-6))
    )
    if confidence < 0.55:
        return []

    return [
        PresetCandidate(
            preset="textSlantUp" if angle > 0 else "textSlantDown",
            confidence=confidence,
            parameters={"angle": angle},
            reason="Linear baseline with significant slope",
        )
    ]


def classify_polygonal(
    text_path: TextPathFrame, features: PathFeatures
) -> list[PresetCandidate]:
    if features.corner_count < 3:
        return []
    if features.line_command_count < 3 and features.command_counts.get("L", 0) < 3:
        return []

    orientation = (
        "clockwise" if features.orientation == "clockwise" else "counter_clockwise"
    )
    confidence = min(
        0.9, max(0.0, features.corner_count / max(features.point_count, 1))
    )
    if confidence < 0.55:
        return []

    return [
        PresetCandidate(
            preset="textCanUp" if orientation == "clockwise" else "textCanDown",
            confidence=confidence,
            parameters={"corners": features.corner_count},
            reason="Polygonal baseline with clear corners",
        )
    ]


__all__ = [
    "classify_arch_family",
    "classify_bulge_family",
    "classify_circle",
    "classify_linear",
    "classify_polygonal",
    "classify_wave_family",
    "collect_candidates",
    "select_best_candidate",
    "side_orientation",
]
