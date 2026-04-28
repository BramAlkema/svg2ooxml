"""Path warp fitting facade for WordArt native conversion."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from svg2ooxml.ir.text_path import PathPoint

from .path_warp_families import fit_arch, fit_bulge, fit_wave
from .path_warp_math import (
    PointTuple,
    determine_arch_direction,
    estimate_wave_parameters,
    fit_circle,
    fit_ellipse,
    fit_linear_baseline,
    fit_quadratic,
)
from .path_warp_types import (
    EXCELLENT_THRESHOLD,
    FAIR_THRESHOLD,
    GOOD_THRESHOLD,
    TextPathPositioner,
    WarpFitResult,
    classify_fit_quality,
    no_fit_result,
)


class PathWarpFitter:
    """Fit sampled paths to arch, wave, or bulge WordArt warp families."""

    EXCELLENT_THRESHOLD = EXCELLENT_THRESHOLD
    GOOD_THRESHOLD = GOOD_THRESHOLD
    FAIR_THRESHOLD = FAIR_THRESHOLD

    def __init__(self, positioner: TextPathPositioner):
        self.positioner = positioner
        self.logger = logging.getLogger(__name__)

    def fit_path_to_warp(
        self,
        path_data: str,
        min_confidence: float = 0.60,
    ) -> WarpFitResult:
        """Fit path data to the best matching WordArt warp preset family."""

        samples = self.positioner.sample_path_for_text(path_data, num_samples=50)
        if len(samples) < 10:
            return self._no_fit_result("Insufficient path samples")

        candidates = [
            self._fit_arch(samples),
            self._fit_wave(samples),
            self._fit_bulge(samples),
        ]
        best_fit = max(candidates, key=lambda fit: fit.confidence)

        if best_fit.confidence < min_confidence:
            return self._no_fit_result("Below confidence threshold")

        best_fit.fit_quality = self._classify_fit_quality(best_fit.confidence)
        return best_fit

    def _fit_arch(self, samples: Sequence[PathPoint]) -> WarpFitResult:
        return fit_arch(samples, self.logger)

    def _fit_wave(self, samples: Sequence[PathPoint]) -> WarpFitResult:
        return fit_wave(samples, self.logger)

    def _fit_bulge(self, samples: Sequence[PathPoint]) -> WarpFitResult:
        return fit_bulge(samples, self.logger)

    def _fit_circle(self, points: Sequence[PointTuple]) -> dict[str, float]:
        return fit_circle(points)

    def _fit_ellipse(self, points: Sequence[PointTuple]) -> dict[str, float]:
        return fit_ellipse(points)

    def _fit_linear_baseline(
        self,
        x_values: Sequence[float],
        y_values: Sequence[float],
    ) -> dict[str, float]:
        return fit_linear_baseline(x_values, y_values)

    def _estimate_wave_parameters(
        self,
        x_values: Sequence[float],
        y_values: Sequence[float],
    ) -> dict[str, float]:
        return estimate_wave_parameters(x_values, y_values)

    def _fit_quadratic(
        self,
        x_values: Sequence[float],
        y_values: Sequence[float],
    ) -> dict[str, float]:
        return fit_quadratic(x_values, y_values)

    def _determine_arch_direction(self, samples: Sequence[PathPoint]) -> str:
        return determine_arch_direction(samples)

    def _classify_fit_quality(self, confidence: float) -> str:
        return classify_fit_quality(confidence)

    def _no_fit_result(self, reason: str) -> WarpFitResult:
        return no_fit_result(reason)


def create_path_warp_fitter(
    positioner: TextPathPositioner | None = None,
) -> PathWarpFitter:
    """Create a path warp fitter with a curve text positioner."""

    if positioner is None:
        from svg2ooxml.common.geometry.algorithms.curve_text_positioning import (
            PathSamplingMethod,
            create_curve_text_positioner,
        )

        positioner = create_curve_text_positioner(PathSamplingMethod.DETERMINISTIC)

    return PathWarpFitter(positioner)


__all__ = ["PathWarpFitter", "WarpFitResult", "create_path_warp_fitter"]
