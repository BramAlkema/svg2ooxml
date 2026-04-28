"""Compatibility facade for path simplification helpers."""

from __future__ import annotations

from svg2ooxml.common.geometry.points import (
    dot_vectors,
    normalize_vector,
    point_distance,
    point_to_line_distance,
    points_collinear_by_angle,
    vector_between,
)
from svg2ooxml.common.geometry.simplify_curve import (
    chord_length_parameterize,
    compute_max_error,
    curve_fit,
    eval_bezier,
    fit_cubic_beziers,
    fit_single_cubic,
)
from svg2ooxml.common.geometry.simplify_passes import (
    demote_flat_beziers,
    merge_collinear,
    remove_degenerates,
)
from svg2ooxml.common.geometry.simplify_pipeline import (
    DEFAULT_BEZIER_FLATNESS,
    DEFAULT_COLLINEAR_ANGLE,
    DEFAULT_CURVE_FIT_MIN_POINTS,
    DEFAULT_CURVE_FIT_TOLERANCE,
    DEFAULT_EPSILON,
    DEFAULT_RDP_TOLERANCE,
    simplify_segments,
)
from svg2ooxml.common.geometry.simplify_rdp import rdp_points, rdp_simplify
from svg2ooxml.common.geometry.simplify_runs import (
    map_line_runs,
    run_to_points,
    split_subpaths,
)

_chord_length_parameterize = chord_length_parameterize
_collinear = points_collinear_by_angle
_compute_max_error = compute_max_error
_curve_fit = curve_fit
_demote_flat_beziers = demote_flat_beziers
_dist = point_distance
_dot = dot_vectors
_eval_bezier = eval_bezier
_fit_cubic_beziers = fit_cubic_beziers
_fit_single_cubic = fit_single_cubic
_map_line_runs = map_line_runs
_merge_collinear = merge_collinear
_normalize = normalize_vector
_point_to_line_dist = point_to_line_distance
_rdp_points = rdp_points
_rdp_simplify = rdp_simplify
_remove_degenerates = remove_degenerates
_run_to_points = run_to_points
_split_subpaths = split_subpaths
_sub = vector_between

__all__ = [
    "DEFAULT_BEZIER_FLATNESS",
    "DEFAULT_COLLINEAR_ANGLE",
    "DEFAULT_CURVE_FIT_MIN_POINTS",
    "DEFAULT_CURVE_FIT_TOLERANCE",
    "DEFAULT_EPSILON",
    "DEFAULT_RDP_TOLERANCE",
    "_chord_length_parameterize",
    "_collinear",
    "_compute_max_error",
    "_curve_fit",
    "_demote_flat_beziers",
    "_dist",
    "_dot",
    "_eval_bezier",
    "_fit_cubic_beziers",
    "_fit_single_cubic",
    "_map_line_runs",
    "_merge_collinear",
    "_normalize",
    "_point_to_line_dist",
    "_rdp_points",
    "_rdp_simplify",
    "_remove_degenerates",
    "_run_to_points",
    "_split_subpaths",
    "_sub",
    "simplify_segments",
]
