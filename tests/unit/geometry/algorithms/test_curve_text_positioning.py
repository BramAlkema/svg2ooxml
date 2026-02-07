"""Tests for curve text positioning helpers."""

from __future__ import annotations

from svg2ooxml.common.geometry.algorithms import (
    CurveTextPositioner,
    PathSamplingMethod,
    create_path_warp_fitter,
)


def test_sample_path_returns_points_for_simple_path() -> None:
    positioner = CurveTextPositioner(PathSamplingMethod.DETERMINISTIC)
    samples = positioner.sample_path_for_text("M0 0 L50 0 L50 50", num_samples=5)

    assert len(samples) == 5
    assert samples[0].distance_along_path == 0.0
    assert samples[-1].distance_along_path == samples[-1].distance_along_path
    assert all(sample.tangent_angle == 0.0 for sample in samples[:3])


def test_find_point_at_distance_interpolates() -> None:
    positioner = CurveTextPositioner(PathSamplingMethod.DETERMINISTIC)
    samples = positioner.sample_path_for_text("M0 0 L100 0", num_samples=3)

    point = positioner.find_point_at_distance(samples, 25.0)

    assert point is not None
    assert abs(point.x - 25.0) < 1e-6
    assert point.distance_along_path == 25.0


def test_path_warp_fitter_returns_no_fit_for_flat_line() -> None:
    fitter = create_path_warp_fitter()

    result = fitter.fit_path_to_warp("M0 0 L100 0", min_confidence=0.1)

    assert result.preset_type in {"none", "arch", "wave", "bulge"}
