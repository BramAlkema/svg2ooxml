"""WordArt warp classification utilities ported from svg2pptx."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from svg2ooxml.ir.text_path import PathPoint, TextPathFrame, TextPathSide


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


@dataclass
class _Candidate:
    preset: str
    confidence: float
    parameters: dict[str, Any]
    reason: str


def classify_text_path_warp(
    text_path: TextPathFrame,
    path_points: Sequence[PathPoint],
    *,
    path_data: str | None = None,
) -> WordArtClassificationResult | None:
    """Classify a sampled text path into a DrawingML warp preset."""

    if not path_points or len(path_points) < 4:
        return None

    features = _compute_features(list(path_points), path_data)
    candidates: list[_Candidate] = []

    candidates.extend(_classify_circle(features))
    candidates.extend(_classify_arch_family(text_path, features))
    candidates.extend(_classify_wave_family(text_path, features))
    candidates.extend(_classify_bulge_family(text_path, features))
    candidates.extend(_classify_linear(text_path, features))
    candidates.extend(_classify_polygonal(text_path, features))

    best = max(candidates, key=lambda c: c.confidence, default=None)
    if not best or best.confidence < 0.55:
        return None

    feature_summary = {
        "is_closed": features.is_closed,
        "point_count": features.point_count,
        "aspect_ratio": features.aspect_ratio(),
        "peak_count": features.peak_count,
        "trough_count": features.trough_count,
        "corner_count": features.corner_count,
        "orientation": features.orientation,
    }
    return WordArtClassificationResult(
        preset=best.preset,
        confidence=min(best.confidence, 0.99),
        parameters=best.parameters,
        reason=best.reason,
        features=feature_summary,
    )


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def _compute_features(points: list[PathPoint], path_data: str | None) -> PathFeatures:
    xs = [p.x for p in points]
    ys = [p.y for p in points]

    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    x_range = x_max - x_min
    y_range = y_max - y_min

    slope, intercept = _linear_regression(xs, ys)
    slope_degrees = math.degrees(math.atan(slope)) if not math.isclose(slope, 0.0, abs_tol=1e-6) else 0.0

    slopes = _pairwise_slopes(xs, ys)
    curvature_sign_changes = _count_sign_changes(slopes)

    peak_count, trough_count = _count_extrema(ys)
    corner_count = _count_corners(xs, ys)
    zero_crossings = _count_zero_crossings([y - sum(ys) / len(ys) for y in ys])

    is_closed = _path_is_closed(points)
    orientation = _determine_orientation(points)

    command_counts = Counter()
    if path_data:
        commands = re.findall(r"[MmLlHhVvQqCcSsTtAaZz]", path_data)
        command_counts.update(cmd.upper() for cmd in commands)

    amplitude = (max(ys) - min(ys)) / 2 if ys else 0.0
    mean_y = sum(ys) / len(ys) if ys else 0.0
    std_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys) / len(ys)) if ys else 0.0
    x_variance = _variance(xs)
    y_variance = _variance(ys)

    return PathFeatures(
        is_closed=is_closed,
        point_count=len(points),
        x_range=x_range,
        y_range=y_range,
        slope=slope,
        intercept=intercept,
        slope_degrees=slope_degrees,
        curvature_sign_changes=curvature_sign_changes,
        peak_count=peak_count,
        trough_count=trough_count,
        corner_count=corner_count,
        zero_crossings=zero_crossings,
        arc_command_count=command_counts.get("A", 0),
        line_command_count=command_counts.get("L", 0),
        command_counts=command_counts,
        orientation=orientation,
        amplitude=amplitude,
        mean_y=mean_y,
        std_y=std_y,
        x_variance=x_variance,
        y_variance=y_variance,
    )


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------


def _classify_circle(features: PathFeatures) -> list[_Candidate]:
    if not features.is_closed or features.point_count < 16:
        return []

    ratio = features.aspect_ratio()
    ratio_conf = max(0.0, 1.0 - abs(1.0 - ratio))
    variance_conf = max(0.0, 1.0 - (features.std_y / max(features.y_range, 1e-6)))
    confidence = min(0.95, (ratio_conf + variance_conf) / 2)
    if confidence < 0.55:
        return []

    preset = "textCircle"
    reason = "Closed near-circular baseline"
    return [
        _Candidate(
            preset=preset,
            confidence=confidence,
            parameters={},
            reason=reason,
        )
    ]


def _classify_arch_family(text_path: TextPathFrame, features: PathFeatures) -> list[_Candidate]:
    if features.curvature_sign_changes > 2 or features.y_range < 1e-3:
        return []

    direction = "up" if features.slope_degrees >= 0 else "down"
    preset = "textArchUp" if direction == "up" else "textArchDown"
    confidence = max(0.0, 1.0 - features.std_y * 2)

    if text_path.side == TextPathSide.RIGHT:
        confidence *= 0.95

    if confidence < 0.55:
        return []

    return [
        _Candidate(
            preset=preset,
            confidence=confidence,
            parameters={"slope": features.slope, "orientation": features.orientation},
            reason="Smooth monotonic curvature",
        )
    ]


def _classify_wave_family(text_path: TextPathFrame, features: PathFeatures) -> list[_Candidate]:
    if features.is_closed or features.peak_count + features.trough_count < 2 or features.y_range < 1e-3:
        return []

    normalized_amp = features.amplitude / max(features.y_range, 1e-6)
    confidence = max(0.0, min(0.95, normalized_amp * 1.2))
    preset = "textWave1"

    if confidence < 0.55:
        return []

    return [
        _Candidate(
            preset=preset,
            confidence=confidence,
            parameters={"amplitude": features.amplitude},
            reason="Baseline exhibits wave-like oscillation",
        )
    ]


def _classify_bulge_family(text_path: TextPathFrame, features: PathFeatures) -> list[_Candidate]:
    if features.is_closed or features.peak_count + features.trough_count != 1 or features.y_range < 1e-3:
        return []

    direction = "up" if features.peak_count == 1 else "down"
    preset = "textInflate" if direction == "up" else "textDeflate"
    confidence = max(0.0, 1.0 - features.std_y)

    if confidence < 0.55:
        return []

    return [
        _Candidate(
            preset=preset,
            confidence=confidence,
            parameters={"direction": direction},
            reason="Single apex baseline (bulge)",
        )
    ]


def _classify_linear(text_path: TextPathFrame, features: PathFeatures) -> list[_Candidate]:
    confidence = max(0.0, min(0.95, 1.0 - features.std_y * 10))
    preset = "textPlain"
    if confidence < 0.55:
        return []
    parameters: dict[str, Any] = {"slope": features.slope}
    if text_path.side == TextPathSide.RIGHT:
        parameters["mirror"] = True
    return [
        _Candidate(
            preset=preset,
            confidence=confidence,
            parameters=parameters,
            reason="Low curvature baseline",
        )
    ]


def _classify_polygonal(text_path: TextPathFrame, features: PathFeatures) -> list[_Candidate]:
    if features.corner_count < 2:
        return []
    preset = "textTriangle" if features.corner_count == 2 else "textChevronUp"
    confidence = min(0.9, 0.6 + features.corner_count * 0.1)
    return [
        _Candidate(
            preset=preset,
            confidence=confidence,
            parameters={"corner_count": features.corner_count},
            reason="Detected polygonal baseline with sharp corners",
        )
    ]


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------


def _linear_regression(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
    if not xs or not ys or len(xs) != len(ys):
        return 0.0, 0.0
    n = len(xs)
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_x2 = sum(x * x for x in xs)
    denom = n * sum_x2 - sum_x * sum_x
    if abs(denom) < 1e-9:
        return 0.0, sum_y / n
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    return slope, intercept


def _pairwise_slopes(xs: Sequence[float], ys: Sequence[float]) -> list[float]:
    slopes = []
    for i in range(1, len(xs)):
        dx = xs[i] - xs[i - 1]
        dy = ys[i] - ys[i - 1]
        if abs(dx) < 1e-9:
            slopes.append(float("inf") if dy > 0 else float("-inf"))
        else:
            slopes.append(dy / dx)
    return slopes


def _count_sign_changes(values: Sequence[float]) -> int:
    signs: list[int] = []
    for value in values:
        if math.isinf(value) or abs(value) < 1e-6:
            continue
        signs.append(1 if value > 0 else -1)
    flips = 0
    for i in range(1, len(signs)):
        if signs[i] != signs[i - 1]:
            flips += 1
    return flips


def _count_extrema(values: Sequence[float]) -> tuple[int, int]:
    peaks = 0
    troughs = 0
    for i in range(1, len(values) - 1):
        prev_y, curr_y, next_y = values[i - 1], values[i], values[i + 1]
        if curr_y > prev_y and curr_y > next_y:
            peaks += 1
        elif curr_y < prev_y and curr_y < next_y:
            troughs += 1
    return peaks, troughs


def _count_corners(xs: Sequence[float], ys: Sequence[float]) -> int:
    if len(xs) < 3:
        return 0
    corners = 0
    for i in range(1, len(xs) - 1):
        v1 = (xs[i] - xs[i - 1], ys[i] - ys[i - 1])
        v2 = (xs[i + 1] - xs[i], ys[i + 1] - ys[i])
        if _vector_angle(v1, v2) > math.radians(25):
            corners += 1
    return corners


def _count_zero_crossings(values: Sequence[float]) -> int:
    crossings = 0
    for i in range(1, len(values)):
        if values[i - 1] == 0:
            continue
        if values[i - 1] * values[i] < 0:
            crossings += 1
    return crossings


def _variance(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _path_is_closed(points: Sequence[PathPoint]) -> bool:
    first, last = points[0], points[-1]
    distance = math.hypot(last.x - first.x, last.y - first.y)
    return distance < 1e-2


def _determine_orientation(points: Sequence[PathPoint]) -> str:
    if points[-1].x < points[0].x:
        return "right-to-left"
    return "left-to-right"


def _vector_angle(v1: tuple[float, float], v2: tuple[float, float]) -> float:
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    len1 = math.hypot(*v1)
    len2 = math.hypot(*v2)
    if len1 == 0 or len2 == 0:
        return 0.0
    cos_angle = max(-1.0, min(1.0, dot / (len1 * len2)))
    return math.acos(cos_angle)


__all__ = [
    "WordArtClassificationResult",
    "PathFeatures",
    "classify_text_path_warp",
]
