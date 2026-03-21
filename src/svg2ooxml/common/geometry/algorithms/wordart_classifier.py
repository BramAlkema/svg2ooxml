"""WordArt warp classification utilities ported from svg2pptx."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from svg2ooxml.common.math_utils import population_variance

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


def _side_orientation(text_path: TextPathFrame) -> int:
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


def _summarise_features(features: PathFeatures) -> dict[str, Any]:
    return {
        "is_closed": features.is_closed,
        "point_count": features.point_count,
        "aspect_ratio": features.aspect_ratio(),
        "peak_count": features.peak_count,
        "trough_count": features.trough_count,
        "corner_count": features.corner_count,
        "orientation": features.orientation,
    }


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
            features=_summarise_features(features),
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
            features=_summarise_features(features),
        )

    candidates: list[_Candidate] = []

    candidates.extend(_classify_circle(features))
    candidates.extend(_classify_arch_family(text_path, features))
    candidates.extend(_classify_wave_family(text_path, features))
    candidates.extend(_classify_bulge_family(text_path, features))
    candidates.extend(_classify_linear(text_path, features))
    candidates.extend(_classify_polygonal(text_path, features))

    wave_candidates = [c for c in candidates if c.preset == "textWave1"]
    if features.zero_crossings >= 2 and not features.is_closed and wave_candidates:
        best = max(wave_candidates, key=lambda c: c.confidence, default=None)
    else:
        best = max(candidates, key=lambda c: c.confidence, default=None)
    if not best or best.confidence < 0.40:
        return None

    feature_summary = _summarise_features(features)
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
    x_variance = population_variance(xs)
    y_variance = population_variance(ys)

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
    if (
        features.curvature_sign_changes > 2
        or features.y_range < 1e-3
        or features.peak_count > 1
        or features.trough_count > 1
        or features.zero_crossings > 2  # arches naturally cross mean Y twice
    ):
        return []

    orientation = _side_orientation(text_path)
    amplitude = features.amplitude

    # Confidence based on how arch-like the curve is: single peak or trough,
    # consistent curvature direction, reasonable amplitude relative to span.
    y_span = features.y_range
    arch_ratio = amplitude / max(y_span, 1e-6)  # how much of the range is the arch
    curvature_consistency = max(0.0, 1.0 - features.curvature_sign_changes * 0.3)
    confidence = min(0.95, (arch_ratio + curvature_consistency) / 2)
    if confidence < 0.4:
        return []

    preset = "textArchUp" if orientation > 0 else "textArchDown"
    parameters = {"amplitude": amplitude * orientation}

    return [
        _Candidate(
            preset=preset,
            confidence=confidence,
            parameters=parameters,
            reason="Arch-like baseline with consistent curvature",
        )
    ]


def _classify_wave_family(text_path: TextPathFrame, features: PathFeatures) -> list[_Candidate]:
    if features.curvature_sign_changes < 2:
        return []

    is_horizontal = abs(features.slope) < 0.05
    if not is_horizontal:
        return []

    amplitude = features.amplitude
    zero_crossings = features.zero_crossings

    if zero_crossings >= 2 and not features.is_closed:
        confidence = 0.85
    else:
        confidence = min(0.95, amplitude / max(features.y_range, 1e-6))
    if confidence < 0.55:
        return []

    preset = "textWave1"
    return [
        _Candidate(
            preset=preset,
            confidence=confidence,
            parameters={"amplitude": amplitude},
            reason="Wave-like oscillation with multiple zero crossings",
        )
    ]


def _classify_bulge_family(text_path: TextPathFrame, features: PathFeatures) -> list[_Candidate]:
    if features.curvature_sign_changes > 2 or features.point_count < 12:
        return []

    orientation = _side_orientation(text_path)
    amplitude = features.amplitude

    confidence = min(0.9, max(0.0, amplitude / max(features.y_range, 1e-6)))
    if confidence < 0.55:
        return []

    preset = "textInflateTop" if orientation > 0 else "textInflateBottom"
    return [
        _Candidate(
            preset=preset,
            confidence=confidence,
            parameters={"amplitude": amplitude * orientation},
            reason="Bulge-like baseline with smooth curvature",
        )
    ]


def _classify_linear(text_path: TextPathFrame, features: PathFeatures) -> list[_Candidate]:
    if features.curvature_sign_changes > 0 or abs(features.slope) < 0.01:
        return []

    angle = math.degrees(math.atan(features.slope))
    confidence = min(0.9, max(0.0, 1.0 - abs(features.std_y) / max(features.y_range, 1e-6)))
    if confidence < 0.55:
        return []

    preset = "textSlantUp" if angle > 0 else "textSlantDown"
    return [
        _Candidate(
            preset=preset,
            confidence=confidence,
            parameters={"angle": angle},
            reason="Linear baseline with significant slope",
        )
    ]


def _classify_polygonal(text_path: TextPathFrame, features: PathFeatures) -> list[_Candidate]:
    if features.corner_count < 3:
        return []
    if features.line_command_count < 3 and features.command_counts.get("L", 0) < 3:
        return []

    orientation = "clockwise" if features.orientation == "clockwise" else "counter_clockwise"
    confidence = min(0.9, max(0.0, features.corner_count / max(features.point_count, 1)))
    if confidence < 0.55:
        return []

    preset = "textCanUp" if orientation == "clockwise" else "textCanDown"
    return [
        _Candidate(
            preset=preset,
            confidence=confidence,
            parameters={"corners": features.corner_count},
            reason="Polygonal baseline with clear corners",
        )
    ]


# ---------------------------------------------------------------------------
# Feature utilities
# ---------------------------------------------------------------------------


def _linear_regression(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
    n = len(xs)
    if n == 0:
        return 0.0, 0.0

    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys, strict=True))
    sum_x2 = sum(x * x for x in xs)

    denominator = n * sum_x2 - sum_x ** 2
    if abs(denominator) < 1e-12:
        return 0.0, sum_y / n if n > 0 else 0.0

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n
    return slope, intercept


def _pairwise_slopes(xs: Sequence[float], ys: Sequence[float]) -> list[float]:
    slopes: list[float] = []
    for i in range(1, len(xs)):
        dx = xs[i] - xs[i - 1]
        dy = ys[i] - ys[i - 1]
        if abs(dx) < 1e-6:
            slopes.append(float("inf"))
        else:
            slopes.append(dy / dx)
    return slopes


def _count_sign_changes(values: Sequence[float]) -> int:
    count = 0
    prev_sign = None
    for value in values:
        if math.isinf(value):
            continue
        sign = 1 if value > 0 else -1 if value < 0 else 0
        if prev_sign is not None and sign != 0 and sign != prev_sign:
            count += 1
        if sign != 0:
            prev_sign = sign
    return count


def _count_extrema(values: Sequence[float]) -> tuple[int, int]:
    peaks = 0
    troughs = 0
    for i in range(1, len(values) - 1):
        if values[i - 1] < values[i] > values[i + 1]:
            peaks += 1
        elif values[i - 1] > values[i] < values[i + 1]:
            troughs += 1
    return peaks, troughs


def _count_corners(xs: Sequence[float], ys: Sequence[float]) -> int:
    corners = 0
    for i in range(1, len(xs) - 1):
        dx1 = xs[i] - xs[i - 1]
        dy1 = ys[i] - ys[i - 1]
        dx2 = xs[i + 1] - xs[i]
        dy2 = ys[i + 1] - ys[i]

        dot = dx1 * dx2 + dy1 * dy2
        mag1 = math.sqrt(dx1 ** 2 + dy1 ** 2)
        mag2 = math.sqrt(dx2 ** 2 + dy2 ** 2)

        if mag1 * mag2 == 0:
            continue

        cos_angle = dot / (mag1 * mag2)
        angle = math.degrees(math.acos(max(-1.0, min(1.0, cos_angle))))

        if angle < 120.0:  # Tight angle threshold
            corners += 1
    return corners


def _count_zero_crossings(values: Sequence[float]) -> int:
    count = 0
    for i in range(1, len(values)):
        if values[i - 1] == 0 or values[i] == 0:
            continue
        if (values[i - 1] < 0 < values[i]) or (values[i - 1] > 0 > values[i]):
            count += 1
    return count


def _path_is_closed(points: Sequence[PathPoint]) -> bool:
    if not points:
        return False
    start = points[0]
    end = points[-1]
    return math.isclose(start.x, end.x, abs_tol=1e-6) and math.isclose(start.y, end.y, abs_tol=1e-6)


def _determine_orientation(points: Sequence[PathPoint]) -> str:
    area = 0.0
    for i in range(len(points) - 1):
        area += points[i].x * points[i + 1].y - points[i + 1].x * points[i].y
    return "clockwise" if area < 0 else "counter_clockwise"


__all__ = ["PathFeatures", "WordArtClassificationResult", "classify_text_path_warp"]
