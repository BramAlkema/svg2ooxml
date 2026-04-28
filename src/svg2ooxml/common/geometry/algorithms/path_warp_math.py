"""Numeric helpers for path-to-WordArt warp fitting."""

from __future__ import annotations

import math
from collections.abc import Sequence

from svg2ooxml.ir.text_path import PathPoint

from .wordart_features import count_zero_crossings, linear_regression

PointTuple = tuple[float, float]


def samples_to_xy(samples: Sequence[PathPoint]) -> tuple[list[float], list[float]]:
    return [sample.x for sample in samples], [sample.y for sample in samples]


def rms_error(actual: Sequence[float], predicted: Sequence[float]) -> float:
    if not actual:
        return float("inf")
    return math.sqrt(
        sum((a - p) ** 2 for a, p in zip(actual, predicted, strict=True)) / len(actual)
    )


def confidence_from_error(error: float, values: Sequence[float]) -> float:
    if not values:
        return 0.0
    value_range = max(values) - min(values)
    return max(0.0, 1.0 - (error / max(value_range, 1.0)))


def fit_circle(points: Sequence[PointTuple]) -> dict[str, float]:
    """Fit a circle using an algebraic centroid/radius approximation."""

    point_count = len(points)
    center_x = sum(point[0] for point in points) / point_count
    center_y = sum(point[1] for point in points) / point_count

    radii = [math.hypot(point[0] - center_x, point[1] - center_y) for point in points]
    average_radius = sum(radii) / point_count
    error = math.sqrt(
        sum((radius - average_radius) ** 2 for radius in radii) / point_count
    )
    confidence = max(0.0, 1.0 - (error / max(average_radius, 1.0)))

    return {
        "center_x": center_x,
        "center_y": center_y,
        "radius": average_radius,
        "error": error,
        "confidence": confidence,
    }


def fit_ellipse(points: Sequence[PointTuple]) -> dict[str, float]:
    """Fit an ellipse using the existing circle approximation."""

    circle_fit = fit_circle(points)
    return {
        "center_x": circle_fit["center_x"],
        "center_y": circle_fit["center_y"],
        "radius_x": circle_fit["radius"],
        "radius_y": circle_fit["radius"],
        "error": circle_fit["error"],
        "confidence": min(1.0, circle_fit["confidence"] * 1.1),
    }


def fit_linear_baseline(
    x_values: Sequence[float],
    y_values: Sequence[float],
) -> dict[str, float]:
    """Fit a linear baseline using the shared WordArt regression helper."""

    slope, intercept = linear_regression(x_values, y_values)
    return {"slope": slope, "intercept": intercept}


def estimate_wave_parameters(
    x_values: Sequence[float],
    y_values: Sequence[float],
) -> dict[str, float]:
    if not y_values or not x_values:
        return {"amplitude": 0.0, "frequency": 0.0, "phase": 0.0}

    amplitude = (max(y_values) - min(y_values)) / 2
    zero_crossings = count_zero_crossings(y_values)

    x_range = max(x_values) - min(x_values)
    if x_range > 0 and zero_crossings > 1:
        frequency = zero_crossings / (2 * x_range)
    else:
        frequency = 1.0 / max(x_range, 1.0)

    return {
        "amplitude": amplitude,
        "frequency": frequency,
        "phase": 0.0,
    }


def fit_quadratic(
    x_values: Sequence[float],
    y_values: Sequence[float],
) -> dict[str, float]:
    """Fit quadratic coefficients for ``y = ax^2 + bx + c``."""

    point_count = len(x_values)
    sum_x = sum(x_values)
    sum_x2 = sum(x * x for x in x_values)
    sum_x4 = sum(x * x * x * x for x in x_values)
    sum_y = sum(y_values)
    sum_xy = sum(x * y for x, y in zip(x_values, y_values, strict=True))
    sum_x2y = sum(x * x * y for x, y in zip(x_values, y_values, strict=True))

    try:
        c = sum_y / point_count
        b = (sum_xy - c * sum_x) / max(sum_x2, 1.0)
        a = (sum_x2y - b * sum_x2 - c * sum_x) / max(sum_x4, 1.0)
        return {"a": a, "b": b, "c": c}
    except Exception:
        return {"a": 0.0, "b": 0.0, "c": sum_y / max(point_count, 1)}


def determine_arch_direction(samples: Sequence[PathPoint]) -> str:
    if len(samples) < 3:
        return "up"

    start_y = samples[0].y
    end_y = samples[-1].y
    mid_y = samples[len(samples) // 2].y
    baseline_y = (start_y + end_y) / 2

    return "up" if mid_y > baseline_y else "down"


__all__ = [
    "PointTuple",
    "confidence_from_error",
    "determine_arch_direction",
    "estimate_wave_parameters",
    "fit_circle",
    "fit_ellipse",
    "fit_linear_baseline",
    "fit_quadratic",
    "rms_error",
    "samples_to_xy",
]
