"""Parametric warp-family fitting functions."""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence

from svg2ooxml.ir.text_path import PathPoint

from .path_warp_math import (
    confidence_from_error,
    determine_arch_direction,
    estimate_wave_parameters,
    fit_circle,
    fit_ellipse,
    fit_linear_baseline,
    fit_quadratic,
    rms_error,
    samples_to_xy,
)
from .path_warp_types import WarpFitResult, poor_fit_result


def fit_arch(
    samples: Sequence[PathPoint],
    logger: logging.Logger | None = None,
) -> WarpFitResult:
    """Fit path samples to an arch-like circle or ellipse family."""

    if len(samples) < 3:
        return poor_fit_result("arch")

    try:
        points = [(sample.x, sample.y) for sample in samples]
        circle_result = fit_circle(points)
        ellipse_result = fit_ellipse(points)
        direction = determine_arch_direction(samples)

        if circle_result["confidence"] > ellipse_result["confidence"]:
            return WarpFitResult(
                preset_type="arch",
                confidence=circle_result["confidence"],
                error_metric=circle_result["error"],
                parameters={
                    "shape": "circle",
                    "radius": circle_result["radius"],
                    "center_x": circle_result["center_x"],
                    "center_y": circle_result["center_y"],
                    "direction": direction,
                },
                fit_quality="unknown",
            )

        return WarpFitResult(
            preset_type="arch",
            confidence=ellipse_result["confidence"],
            error_metric=ellipse_result["error"],
            parameters={
                "shape": "ellipse",
                "radius_x": ellipse_result["radius_x"],
                "radius_y": ellipse_result["radius_y"],
                "center_x": ellipse_result["center_x"],
                "center_y": ellipse_result["center_y"],
                "direction": direction,
            },
            fit_quality="unknown",
        )
    except Exception as exc:
        if logger is not None:
            logger.debug("Arch fitting failed: %s", exc)
        return poor_fit_result("arch")


def fit_wave(
    samples: Sequence[PathPoint],
    logger: logging.Logger | None = None,
) -> WarpFitResult:
    """Fit path samples to a sine wave family."""

    if len(samples) < 5:
        return poor_fit_result("wave")

    try:
        x_values, y_values = samples_to_xy(samples)
        baseline = fit_linear_baseline(x_values, y_values)
        detrended_y = [
            y - (baseline["slope"] * x + baseline["intercept"])
            for x, y in zip(x_values, y_values, strict=True)
        ]
        wave_params = estimate_wave_parameters(x_values, detrended_y)

        predicted_y = [
            wave_params["amplitude"]
            * math.sin(
                2 * math.pi * wave_params["frequency"] * x + wave_params["phase"]
            )
            + baseline["slope"] * x
            + baseline["intercept"]
            for x in x_values
        ]

        error = rms_error(y_values, predicted_y)
        confidence = confidence_from_error(error, y_values)

        return WarpFitResult(
            preset_type="wave",
            confidence=confidence,
            error_metric=error,
            parameters={
                "amplitude": wave_params["amplitude"],
                "frequency": wave_params["frequency"],
                "phase": wave_params["phase"],
                "baseline_slope": baseline["slope"],
                "baseline_intercept": baseline["intercept"],
            },
            fit_quality="unknown",
        )
    except Exception as exc:
        if logger is not None:
            logger.debug("Wave fitting failed: %s", exc)
        return poor_fit_result("wave")


def fit_bulge(
    samples: Sequence[PathPoint],
    logger: logging.Logger | None = None,
) -> WarpFitResult:
    """Fit path samples to a quadratic bulge family."""

    if len(samples) < 3:
        return poor_fit_result("bulge")

    try:
        x_values, y_values = samples_to_xy(samples)
        quadratic_params = fit_quadratic(x_values, y_values)
        predicted_y = [
            quadratic_params["a"] * x**2
            + quadratic_params["b"] * x
            + quadratic_params["c"]
            for x in x_values
        ]

        error = rms_error(y_values, predicted_y)
        confidence = confidence_from_error(error, y_values)

        return WarpFitResult(
            preset_type="bulge",
            confidence=confidence,
            error_metric=error,
            parameters={
                "curvature": quadratic_params["a"],
                "slope": quadratic_params["b"],
                "offset": quadratic_params["c"],
                "direction": "up" if quadratic_params["a"] > 0 else "down",
            },
            fit_quality="unknown",
        )
    except Exception as exc:
        if logger is not None:
            logger.debug("Bulge fitting failed: %s", exc)
        return poor_fit_result("bulge")


__all__ = ["fit_arch", "fit_bulge", "fit_wave"]
