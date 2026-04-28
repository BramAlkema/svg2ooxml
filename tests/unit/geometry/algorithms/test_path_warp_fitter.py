"""Tests for path warp fitting helpers."""

from __future__ import annotations

import math

from svg2ooxml.common.geometry.algorithms.path_warp_families import fit_bulge, fit_wave
from svg2ooxml.common.geometry.algorithms.path_warp_math import (
    estimate_wave_parameters,
    fit_linear_baseline,
)
from svg2ooxml.common.geometry.algorithms.path_warp_types import (
    classify_fit_quality,
    no_fit_result,
)
from svg2ooxml.ir.text_path import PathPoint


def _points(values: list[tuple[float, float]]) -> list[PathPoint]:
    return [
        PathPoint(
            x=x,
            y=y,
            tangent_angle=0.0,
            distance_along_path=index,
        )
        for index, (x, y) in enumerate(values)
    ]


def test_linear_baseline_reuses_degenerate_safe_regression() -> None:
    baseline = fit_linear_baseline([1.0, 1.0, 1.0], [2.0, 4.0, 6.0])

    assert baseline == {"slope": 0.0, "intercept": 4.0}


def test_estimate_wave_parameters_counts_zero_crossings() -> None:
    params = estimate_wave_parameters(
        [0.0, 1.0, 2.0, 3.0, 4.0],
        [-1.0, 1.0, -1.0, 1.0, -1.0],
    )

    assert params["amplitude"] == 1.0
    assert params["frequency"] == 0.5
    assert params["phase"] == 0.0


def test_fit_wave_reports_high_confidence_for_sine_samples() -> None:
    samples = _points([(float(index), math.sin(index)) for index in range(20)])

    result = fit_wave(samples)

    assert result.preset_type == "wave"
    assert result.confidence > 0.35
    assert result.parameters["amplitude"] > 0


def test_fit_bulge_reports_quadratic_direction() -> None:
    samples = _points([(float(index), float(index * index)) for index in range(6)])

    result = fit_bulge(samples)

    assert result.preset_type == "bulge"
    assert result.parameters["direction"] == "up"
    assert result.confidence > 0.5


def test_no_fit_and_quality_helpers() -> None:
    result = no_fit_result("too few samples")

    assert result.preset_type == "none"
    assert result.parameters["reason"] == "too few samples"
    assert classify_fit_quality(0.96) == "excellent"
    assert classify_fit_quality(0.8) == "good"
    assert classify_fit_quality(0.6) == "fair"
    assert classify_fit_quality(0.59) == "poor"
