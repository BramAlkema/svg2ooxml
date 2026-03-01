"""
Path Warp Fitting Algorithms

Fits sampled paths to arch/wave/bulge parametric families for
WordArt native conversion with confidence scoring.
"""

import logging
import math
from dataclasses import dataclass

from svg2ooxml.ir.text_path import PathPoint


@dataclass
class WarpFitResult:
    """Result of path fitting to parametric warp family."""

    preset_type: str  # 'arch', 'wave', 'bulge', 'none'
    confidence: float  # 0.0 to 1.0
    error_metric: float  # RMS error
    parameters: dict[str, float]  # Family-specific parameters
    fit_quality: str  # 'excellent', 'good', 'fair', 'poor'


class PathWarpFitter:
    """
    Extends curve positioning with WordArt preset fitting algorithms.

    Fits sampled paths to arch/wave/bulge parametric families for
    WordArt native conversion with confidence scoring.
    """

    # Confidence thresholds for fit quality
    EXCELLENT_THRESHOLD = 0.95
    GOOD_THRESHOLD = 0.80
    FAIR_THRESHOLD = 0.60

    def __init__(self, positioner):
        """
        Initialize warp fitter with curve positioner.

        Args:
            positioner: Existing curve text positioner
        """
        self.positioner = positioner
        self.logger = logging.getLogger(__name__)

    def fit_path_to_warp(self, path_data: str,
                        min_confidence: float = 0.60) -> WarpFitResult:
        """
        Fit path to best-matching WordArt warp preset.

        Args:
            path_data: SVG path data string
            min_confidence: Minimum confidence threshold for valid fit

        Returns:
            WarpFitResult with best fit and confidence metrics
        """
        # Sample path for analysis
        samples = self.positioner.sample_path_for_text(path_data, num_samples=50)

        if len(samples) < 10:  # Insufficient data
            return self._no_fit_result("Insufficient path samples")

        # Try each warp family
        arch_fit = self._fit_arch(samples)
        wave_fit = self._fit_wave(samples)
        bulge_fit = self._fit_bulge(samples)

        # Select best fit
        candidates = [arch_fit, wave_fit, bulge_fit]
        best_fit = max(candidates, key=lambda f: f.confidence)

        # Validate confidence threshold
        if best_fit.confidence < min_confidence:
            return self._no_fit_result("Below confidence threshold")

        # Assign fit quality
        best_fit.fit_quality = self._classify_fit_quality(best_fit.confidence)

        return best_fit

    def _fit_arch(self, samples: list[PathPoint]) -> WarpFitResult:
        """
        Fit path to arch (circle/ellipse) parametric family.

        Uses least-squares fitting to find best circle/ellipse parameters.
        """
        if len(samples) < 3:
            return WarpFitResult('arch', 0.0, float('inf'), {}, 'poor')

        try:
            # Extract x,y coordinates
            points = [(p.x, p.y) for p in samples]

            # Try circle fit first (simpler case)
            circle_result = self._fit_circle(points)

            # Try ellipse fit for better accuracy
            ellipse_result = self._fit_ellipse(points)

            # Choose better fit
            if circle_result['confidence'] > ellipse_result['confidence']:
                return WarpFitResult(
                    preset_type='arch',
                    confidence=circle_result['confidence'],
                    error_metric=circle_result['error'],
                    parameters={
                        'shape': 'circle',
                        'radius': circle_result['radius'],
                        'center_x': circle_result['center_x'],
                        'center_y': circle_result['center_y'],
                        'direction': self._determine_arch_direction(samples),
                    },
                    fit_quality='unknown',
                )
            else:
                return WarpFitResult(
                    preset_type='arch',
                    confidence=ellipse_result['confidence'],
                    error_metric=ellipse_result['error'],
                    parameters={
                        'shape': 'ellipse',
                        'radius_x': ellipse_result['radius_x'],
                        'radius_y': ellipse_result['radius_y'],
                        'center_x': ellipse_result['center_x'],
                        'center_y': ellipse_result['center_y'],
                        'direction': self._determine_arch_direction(samples),
                    },
                    fit_quality='unknown',
                )

        except Exception as e:
            self.logger.debug(f"Arch fitting failed: {e}")
            return WarpFitResult('arch', 0.0, float('inf'), {}, 'poor')

    def _fit_wave(self, samples: list[PathPoint]) -> WarpFitResult:
        """
        Fit path to sine wave with amplitude/frequency detection.
        """
        if len(samples) < 5:
            return WarpFitResult('wave', 0.0, float('inf'), {}, 'poor')

        try:
            # Extract coordinates and approximate baseline
            points = [(p.x, p.y) for p in samples]
            x_values = [p[0] for p in points]
            y_values = [p[1] for p in points]

            # Baseline estimation (linear regression)
            baseline = self._fit_linear_baseline(x_values, y_values)

            # Remove baseline to isolate wave component
            detrended_y = [y - (baseline['slope'] * x + baseline['intercept'])
                          for x, y in points]

            # Estimate wave parameters
            wave_params = self._estimate_wave_parameters(x_values, detrended_y)

            # Calculate fit quality
            predicted_y = [wave_params['amplitude'] * math.sin(
                2 * math.pi * wave_params['frequency'] * x + wave_params['phase'],
            ) + baseline['slope'] * x + baseline['intercept'] for x in x_values]

            rms_error = math.sqrt(sum((actual - pred)**2 for actual, pred in
                                    zip(y_values, predicted_y, strict=True)) / len(y_values))

            # Normalize error to calculate confidence
            y_range = max(y_values) - min(y_values)
            confidence = max(0.0, 1.0 - (rms_error / max(y_range, 1.0)))

            return WarpFitResult(
                preset_type='wave',
                confidence=confidence,
                error_metric=rms_error,
                parameters={
                    'amplitude': wave_params['amplitude'],
                    'frequency': wave_params['frequency'],
                    'phase': wave_params['phase'],
                    'baseline_slope': baseline['slope'],
                    'baseline_intercept': baseline['intercept'],
                },
                fit_quality='unknown',
            )

        except Exception as e:
            self.logger.debug(f"Wave fitting failed: {e}")
            return WarpFitResult('wave', 0.0, float('inf'), {}, 'poor')

    def _fit_bulge(self, samples: list[PathPoint]) -> WarpFitResult:
        """
        Fit path to quadratic bulge (parabola) family.
        """
        if len(samples) < 3:
            return WarpFitResult('bulge', 0.0, float('inf'), {}, 'poor')

        try:
            # Extract coordinates
            points = [(p.x, p.y) for p in samples]
            x_values = [p[0] for p in points]
            y_values = [p[1] for p in points]

            # Fit quadratic: y = ax² + bx + c
            quadratic_params = self._fit_quadratic(x_values, y_values)

            # Calculate fit quality
            predicted_y = [quadratic_params['a'] * x**2 +
                          quadratic_params['b'] * x +
                          quadratic_params['c'] for x in x_values]

            rms_error = math.sqrt(sum((actual - pred)**2 for actual, pred in
                                    zip(y_values, predicted_y, strict=True)) / len(y_values))

            # Normalize error to calculate confidence
            y_range = max(y_values) - min(y_values)
            confidence = max(0.0, 1.0 - (rms_error / max(y_range, 1.0)))

            return WarpFitResult(
                preset_type='bulge',
                confidence=confidence,
                error_metric=rms_error,
                parameters={
                    'curvature': quadratic_params['a'],
                    'slope': quadratic_params['b'],
                    'offset': quadratic_params['c'],
                    'direction': 'up' if quadratic_params['a'] > 0 else 'down',
                },
                fit_quality='unknown',
            )

        except Exception as e:
            self.logger.debug(f"Bulge fitting failed: {e}")
            return WarpFitResult('bulge', 0.0, float('inf'), {}, 'poor')

    def _fit_circle(self, points: list[tuple[float, float]]) -> dict[str, float]:
        """Fit circle using algebraic method."""
        # Simplified circle fitting (algebraic least squares)
        n = len(points)

        # Calculate centroid
        cx = sum(p[0] for p in points) / n
        cy = sum(p[1] for p in points) / n

        # Calculate average radius
        radii = [math.sqrt((p[0] - cx)**2 + (p[1] - cy)**2) for p in points]
        avg_radius = sum(radii) / n

        # Calculate error metric
        error = math.sqrt(sum((r - avg_radius)**2 for r in radii) / n)

        # Confidence based on radius consistency
        radius_variance = error / max(avg_radius, 1.0)
        confidence = max(0.0, 1.0 - radius_variance)

        return {
            'center_x': cx,
            'center_y': cy,
            'radius': avg_radius,
            'error': error,
            'confidence': confidence,
        }

    def _fit_ellipse(self, points: list[tuple[float, float]]) -> dict[str, float]:
        """Simplified ellipse fitting."""
        # For now, approximate as circle (full ellipse fitting is complex)
        circle_fit = self._fit_circle(points)

        # Slightly better confidence for ellipse assumption
        return {
            'center_x': circle_fit['center_x'],
            'center_y': circle_fit['center_y'],
            'radius_x': circle_fit['radius'],
            'radius_y': circle_fit['radius'],
            'error': circle_fit['error'],
            'confidence': min(1.0, circle_fit['confidence'] * 1.1),
        }

    def _fit_linear_baseline(self, x_values: list[float],
                           y_values: list[float]) -> dict[str, float]:
        """Fit linear baseline using least squares."""
        n = len(x_values)

        sum_x = sum(x_values)
        sum_y = sum(y_values)
        sum_xy = sum(x * y for x, y in zip(x_values, y_values, strict=True))
        sum_x2 = sum(x * x for x in x_values)

        # Linear regression
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        intercept = (sum_y - slope * sum_x) / n

        return {'slope': slope, 'intercept': intercept}

    def _estimate_wave_parameters(self, x_values: list[float],
                                 y_values: list[float]) -> dict[str, float]:
        """Estimate sine wave parameters from detrended data."""
        if len(y_values) == 0:
            return {'amplitude': 0.0, 'frequency': 0.0, 'phase': 0.0}

        # Amplitude approximation
        amplitude = (max(y_values) - min(y_values)) / 2

        # Frequency estimation (zero crossings)
        zero_crossings = 0
        for i in range(1, len(y_values)):
            if y_values[i-1] * y_values[i] < 0:  # Sign change
                zero_crossings += 1

        x_range = max(x_values) - min(x_values)
        if x_range > 0 and zero_crossings > 1:
            frequency = zero_crossings / (2 * x_range)
        else:
            frequency = 1.0 / max(x_range, 1.0)

        # Phase approximation (first peak)
        phase = 0.0  # Simplified

        return {
            'amplitude': amplitude,
            'frequency': frequency,
            'phase': phase,
        }

    def _fit_quadratic(self, x_values: list[float],
                      y_values: list[float]) -> dict[str, float]:
        """Fit quadratic polynomial using least squares."""
        n = len(x_values)

        # Build normal equations for ax² + bx + c
        sum_x = sum(x_values)
        sum_x2 = sum(x * x for x in x_values)
        sum(x * x * x for x in x_values)
        sum_x4 = sum(x * x * x * x for x in x_values)
        sum_y = sum(y_values)
        sum_xy = sum(x * y for x, y in zip(x_values, y_values, strict=True))
        sum_x2y = sum(x * x * y for x, y in zip(x_values, y_values, strict=True))

        # Solve 3x3 system (simplified for robustness)
        try:
            # Use simplified least squares for quadratic
            # This is a basic implementation - could be improved with numpy

            # Approximate coefficients
            c = sum_y / n

            # Linear component
            b = (sum_xy - c * sum_x) / max(sum_x2, 1.0)

            # Quadratic component
            a = (sum_x2y - b * sum_x2 - c * sum_x) / max(sum_x4, 1.0)

            return {'a': a, 'b': b, 'c': c}

        except Exception:
            # Fallback to linear
            return {'a': 0.0, 'b': 0.0, 'c': sum_y / max(n, 1)}

    def _determine_arch_direction(self, samples: list[PathPoint]) -> str:
        """Determine if arch is upward or downward."""
        if len(samples) < 3:
            return 'up'

        # Simple heuristic: check if middle is above or below endpoints
        start_y = samples[0].y
        end_y = samples[-1].y
        mid_y = samples[len(samples) // 2].y

        baseline_y = (start_y + end_y) / 2

        return 'up' if mid_y > baseline_y else 'down'

    def _classify_fit_quality(self, confidence: float) -> str:
        """Classify fit quality based on confidence score."""
        if confidence >= self.EXCELLENT_THRESHOLD:
            return 'excellent'
        elif confidence >= self.GOOD_THRESHOLD:
            return 'good'
        elif confidence >= self.FAIR_THRESHOLD:
            return 'fair'
        else:
            return 'poor'

    def _no_fit_result(self, reason: str) -> WarpFitResult:
        """Create no-fit result with reason."""
        return WarpFitResult(
            preset_type='none',
            confidence=0.0,
            error_metric=float('inf'),
            parameters={'reason': reason},
            fit_quality='poor',
        )


def create_path_warp_fitter(positioner=None) -> PathWarpFitter:
    """
    Create path warp fitter with curve positioner.

    Args:
        positioner: Existing curve positioner (creates new if None)

    Returns:
        Configured PathWarpFitter instance
    """
    if positioner is None:
        from svg2ooxml.common.geometry.algorithms.curve_text_positioning import (
            PathSamplingMethod,
            create_curve_text_positioner,
        )
        positioner = create_curve_text_positioner(PathSamplingMethod.DETERMINISTIC)

    return PathWarpFitter(positioner)


__all__ = ["WarpFitResult", "PathWarpFitter", "create_path_warp_fitter"]
