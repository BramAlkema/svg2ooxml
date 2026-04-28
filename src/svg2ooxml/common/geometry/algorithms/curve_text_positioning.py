"""
Curve Text Positioning Algorithms

Advanced algorithms for positioning text along curved paths, extracted and
modernized from legacy text_path.py implementation. Provides precise
character positioning with proper tangent calculation and path sampling.
"""

from __future__ import annotations

import logging

from svg2ooxml.common.geometry.algorithms.curve_text_metrics import (
    calculate_path_curvature as _calculate_path_curvature,
)
from svg2ooxml.common.geometry.algorithms.curve_text_metrics import (
    find_point_at_distance as _find_point_at_distance,
)
from svg2ooxml.common.geometry.algorithms.curve_text_metrics import (
    interpolate_angle as _interpolate_angle,
)
from svg2ooxml.common.geometry.algorithms.curve_text_parser import (
    create_cubic_segment as _create_cubic_segment,
)
from svg2ooxml.common.geometry.algorithms.curve_text_parser import (
    create_line_segment as _create_line_segment,
)
from svg2ooxml.common.geometry.algorithms.curve_text_parser import (
    create_quadratic_segment as _create_quadratic_segment,
)
from svg2ooxml.common.geometry.algorithms.curve_text_parser import (
    parse_path_commands as _parse_path_commands,
)
from svg2ooxml.common.geometry.algorithms.curve_text_parser import (
    parse_path_segments as _parse_path_segments,
)
from svg2ooxml.common.geometry.algorithms.curve_text_sampling import (
    eval_cubic_at_t as _eval_cubic_at_t,
)
from svg2ooxml.common.geometry.algorithms.curve_text_sampling import (
    eval_line_at_t as _eval_line_at_t,
)
from svg2ooxml.common.geometry.algorithms.curve_text_sampling import (
    eval_quadratic_at_t as _eval_quadratic_at_t,
)
from svg2ooxml.common.geometry.algorithms.curve_text_sampling import (
    fallback_horizontal_line as _fallback_horizontal_line,
)
from svg2ooxml.common.geometry.algorithms.curve_text_sampling import (
    sample_cubic_segment as _sample_cubic_segment,
)
from svg2ooxml.common.geometry.algorithms.curve_text_sampling import (
    sample_line_segment as _sample_line_segment,
)
from svg2ooxml.common.geometry.algorithms.curve_text_sampling import (
    sample_path_deterministic as _sample_path_deterministic,
)
from svg2ooxml.common.geometry.algorithms.curve_text_sampling import (
    sample_path_proportional as _sample_path_proportional,
)
from svg2ooxml.common.geometry.algorithms.curve_text_sampling import (
    sample_quadratic_segment as _sample_quadratic_segment,
)
from svg2ooxml.common.geometry.algorithms.curve_text_sampling import (
    sample_segment as _sample_segment,
)
from svg2ooxml.common.geometry.algorithms.curve_text_sampling import (
    sample_segment_at_distance as _sample_segment_at_distance,
)
from svg2ooxml.common.geometry.algorithms.curve_text_types import (
    PathSamplingMethod,
    PathSegment,
)
from svg2ooxml.common.geometry.algorithms.path_warp_fitter import (  # noqa: F401
    PathWarpFitter,
    WarpFitResult,
    create_path_warp_fitter,
)
from svg2ooxml.ir.text_path import PathPoint


class CurveTextPositioner:
    """
    Advanced curve text positioning using sophisticated path sampling.

    Provides precise character positioning along complex curves with
    proper tangent calculation and adaptive sampling density.
    """

    def __init__(self, sampling_method: PathSamplingMethod = PathSamplingMethod.ADAPTIVE):
        """
        Initialize curve text positioner.

        Args:
            sampling_method: Method for path sampling
        """
        self.sampling_method = sampling_method
        self.default_samples_per_unit = 0.5
        self.logger = logging.getLogger(__name__)

    def sample_path_for_text(
        self,
        path_data: str,
        num_samples: int | None = None,
    ) -> list[PathPoint]:
        """
        Sample path points optimized for text positioning.

        Contract for DETERMINISTIC mode:
        - Always returns exactly num_samples points (including endpoints)
        - distance_along_path is strictly non-decreasing
        - Equal arc-length spacing across entire path

        Args:
            path_data: SVG path data string
            num_samples: Number of samples (auto-calculated if None)

        Returns:
            List of PathPoint objects with position and tangent information
        """
        try:
            segments = self._parse_path_segments(path_data)
            if not segments:
                return self._fallback_horizontal_line(num_samples or 2)

            total_length = sum(segment.length for segment in segments)
            if total_length == 0:
                return self._fallback_horizontal_line(num_samples or 2)

            if num_samples is None:
                if self.sampling_method == PathSamplingMethod.DETERMINISTIC:
                    num_samples = max(
                        2,
                        min(4096, int(total_length * self.default_samples_per_unit)),
                    )
                else:
                    num_samples = max(
                        20,
                        min(200, int(total_length * self.default_samples_per_unit)),
                    )

            if self.sampling_method == PathSamplingMethod.DETERMINISTIC:
                return self._sample_path_deterministic(segments, total_length, num_samples)
            return self._sample_path_proportional(segments, total_length, num_samples)

        except Exception as e:
            self.logger.warning(f"Path sampling failed: {e}")
            return self._fallback_horizontal_line(num_samples or 2)

    def find_point_at_distance(
        self,
        path_points: list[PathPoint],
        target_distance: float,
    ) -> PathPoint | None:
        """
        Find path point at specific distance using interpolation.

        Args:
            path_points: List of sampled path points
            target_distance: Target distance along path

        Returns:
            PathPoint at target distance, or None if not found
        """
        return _find_point_at_distance(path_points, target_distance)

    def calculate_path_curvature(
        self,
        path_points: list[PathPoint],
        point_index: int,
    ) -> float:
        """
        Calculate curvature at a specific path point.

        Args:
            path_points: List of path points
            point_index: Index of point to calculate curvature for

        Returns:
            Curvature value (0 = straight, higher = more curved)
        """
        return _calculate_path_curvature(path_points, point_index)

    _fallback_horizontal_line = staticmethod(_fallback_horizontal_line)
    _sample_path_deterministic = staticmethod(_sample_path_deterministic)
    _sample_path_proportional = staticmethod(_sample_path_proportional)
    _sample_segment_at_distance = staticmethod(_sample_segment_at_distance)
    _eval_line_at_t = staticmethod(_eval_line_at_t)
    _eval_cubic_at_t = staticmethod(_eval_cubic_at_t)
    _eval_quadratic_at_t = staticmethod(_eval_quadratic_at_t)
    _parse_path_segments = staticmethod(_parse_path_segments)
    _parse_path_commands = staticmethod(_parse_path_commands)
    _create_line_segment = staticmethod(_create_line_segment)
    _create_cubic_segment = staticmethod(_create_cubic_segment)
    _create_quadratic_segment = staticmethod(_create_quadratic_segment)
    _sample_segment = staticmethod(_sample_segment)
    _sample_line_segment = staticmethod(_sample_line_segment)
    _sample_cubic_segment = staticmethod(_sample_cubic_segment)
    _sample_quadratic_segment = staticmethod(_sample_quadratic_segment)
    _interpolate_angle = staticmethod(_interpolate_angle)


def create_curve_text_positioner(
    sampling_method: PathSamplingMethod = PathSamplingMethod.ADAPTIVE,
) -> CurveTextPositioner:
    """
    Create curve text positioner with specified sampling method.

    Args:
        sampling_method: Path sampling method

    Returns:
        Configured CurveTextPositioner instance
    """
    return CurveTextPositioner(sampling_method)


__all__ = [
    "CurveTextPositioner",
    "PathSamplingMethod",
    "PathSegment",
    "PathWarpFitter",
    "WarpFitResult",
    "create_curve_text_positioner",
    "create_path_warp_fitter",
]
