"""Compatibility facade for DrawingML motion path helpers."""

from __future__ import annotations

from svg2ooxml.drawingml.animation.handlers.motion_path_parse import (
    bezier_point,
    dedupe_points,
    parse_motion_path,
    resolve_initial_tangent_vector,
    sample_bezier,
    simple_path_parse,
)
from svg2ooxml.drawingml.animation.handlers.motion_path_projection import (
    build_motion_path_string,
    format_coord,
    project_motion_points,
)
from svg2ooxml.drawingml.animation.handlers.motion_path_retime import (
    expand_discrete_points,
    retime_linear_points,
    retime_motion_points,
    sample_points_at_progress,
    sample_polyline_at_distance,
    uniform_key_times,
)
from svg2ooxml.drawingml.animation.handlers.motion_path_tangent import (
    estimate_segment_tangent_angle,
    has_dynamic_rotation,
    resolve_exact_initial_tangent_angle,
    sample_path_tangent_angles,
    unwrap_angles,
)
from svg2ooxml.drawingml.animation.handlers.motion_path_types import PointPair

__all__ = [
    "PointPair",
    "bezier_point",
    "build_motion_path_string",
    "dedupe_points",
    "estimate_segment_tangent_angle",
    "expand_discrete_points",
    "format_coord",
    "has_dynamic_rotation",
    "parse_motion_path",
    "project_motion_points",
    "resolve_exact_initial_tangent_angle",
    "resolve_initial_tangent_vector",
    "retime_linear_points",
    "retime_motion_points",
    "sample_bezier",
    "sample_path_tangent_angles",
    "sample_points_at_progress",
    "sample_polyline_at_distance",
    "simple_path_parse",
    "uniform_key_times",
    "unwrap_angles",
]
