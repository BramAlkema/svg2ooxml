"""Path simplification pipeline orchestration."""

from __future__ import annotations

from collections.abc import Sequence

from svg2ooxml.common.geometry.simplify_curve import curve_fit
from svg2ooxml.common.geometry.simplify_passes import (
    demote_flat_beziers,
    merge_collinear,
    remove_degenerates,
)
from svg2ooxml.common.geometry.simplify_rdp import rdp_simplify
from svg2ooxml.common.geometry.simplify_runs import split_subpaths
from svg2ooxml.ir.geometry import SegmentType

DEFAULT_EPSILON = 0.01
DEFAULT_BEZIER_FLATNESS = 0.5
DEFAULT_COLLINEAR_ANGLE = 0.5
DEFAULT_RDP_TOLERANCE = 1.0
DEFAULT_CURVE_FIT_TOLERANCE = 1.5
DEFAULT_CURVE_FIT_MIN_POINTS = 8


def simplify_segments(
    segments: Sequence[SegmentType],
    *,
    epsilon: float = DEFAULT_EPSILON,
    bezier_flatness: float = DEFAULT_BEZIER_FLATNESS,
    collinear_angle_deg: float = DEFAULT_COLLINEAR_ANGLE,
    rdp_tolerance: float = DEFAULT_RDP_TOLERANCE,
    curve_fit_tolerance: float = DEFAULT_CURVE_FIT_TOLERANCE,
    curve_fit_min_points: int = DEFAULT_CURVE_FIT_MIN_POINTS,
) -> list[SegmentType]:
    """Run simplification passes on *segments*, preserving subpath boundaries."""

    result: list[SegmentType] = []
    for subpath in split_subpaths(list(segments)):
        if len(subpath) <= 1:
            result.extend(subpath)
            continue
        simplified = remove_degenerates(subpath, epsilon)
        simplified = demote_flat_beziers(simplified, bezier_flatness)
        simplified = merge_collinear(simplified, collinear_angle_deg, epsilon)
        if rdp_tolerance > 0:
            simplified = rdp_simplify(simplified, rdp_tolerance, epsilon)
        if curve_fit_tolerance > 0 and curve_fit_min_points > 0:
            simplified = curve_fit(
                simplified,
                curve_fit_tolerance,
                curve_fit_min_points,
                epsilon,
            )
        result.extend(simplified)
    return result


__all__ = [
    "DEFAULT_BEZIER_FLATNESS",
    "DEFAULT_COLLINEAR_ANGLE",
    "DEFAULT_CURVE_FIT_MIN_POINTS",
    "DEFAULT_CURVE_FIT_TOLERANCE",
    "DEFAULT_EPSILON",
    "DEFAULT_RDP_TOLERANCE",
    "simplify_segments",
]
