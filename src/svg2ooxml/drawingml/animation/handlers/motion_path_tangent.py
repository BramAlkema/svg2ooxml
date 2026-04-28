"""Tangent and rotation helpers for motion path animations."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from svg2ooxml.drawingml.animation.handlers.motion_path_parse import (
    resolve_initial_tangent_vector,
)
from svg2ooxml.drawingml.animation.handlers.motion_path_types import PointPair

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition


def sample_path_tangent_angles(
    points: list[PointPair],
    rotate_mode: str,
) -> list[float]:
    """Return unwrapped tangent angles for each sampled motion point."""

    if len(points) < 2:
        return []

    segment_angles = [
        estimate_segment_tangent_angle(points[index], points[index + 1])
        for index in range(len(points) - 1)
    ]
    valid_angles = [angle for angle in segment_angles if angle is not None]
    if not valid_angles:
        return []

    fallback_angle = valid_angles[0]
    normalized_segments: list[float] = []
    for angle in segment_angles:
        resolved_angle = fallback_angle if angle is None else angle
        fallback_angle = resolved_angle
        normalized_segments.append(resolved_angle)

    point_angles = [normalized_segments[0], *normalized_segments]
    if rotate_mode == "auto-reverse":
        point_angles = [angle + 180.0 for angle in point_angles]
    return unwrap_angles(point_angles)


def has_dynamic_rotation(point_angles: list[float]) -> bool:
    if len(point_angles) < 2:
        return False
    return any(
        abs(point_angles[index + 1] - point_angles[index]) > 1e-6
        for index in range(len(point_angles) - 1)
    )


def estimate_segment_tangent_angle(start: PointPair, end: PointPair) -> float | None:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None
    return math.degrees(math.atan2(dy, dx))


def unwrap_angles(angles: list[float]) -> list[float]:
    """Unwrap angle samples so consecutive deltas stay continuous."""

    if not angles:
        return []

    unwrapped = [angles[0]]
    for angle in angles[1:]:
        adjusted = angle
        while adjusted - unwrapped[-1] > 180.0:
            adjusted -= 360.0
        while adjusted - unwrapped[-1] < -180.0:
            adjusted += 360.0
        unwrapped.append(adjusted)
    return unwrapped


def resolve_exact_initial_tangent_angle(
    path_value: str,
    animation: AnimationDefinition,
    rotate_mode: str,
) -> float | None:
    """Resolve the exact tangent angle at the start of the SVG motion path."""

    vector = resolve_initial_tangent_vector(path_value)
    if vector is None:
        return None

    dx, dy = vector
    matrix = animation.motion_space_matrix
    if matrix is not None:
        a, b, c, d, _e, _f = matrix
        dx, dy = (a * dx + c * dy, b * dx + d * dy)

    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None

    angle = math.degrees(math.atan2(dy, dx))
    if rotate_mode == "auto-reverse":
        angle += 180.0
    heading = animation.element_heading_deg
    if heading is not None:
        angle -= heading
    return angle


__all__ = [
    "estimate_segment_tangent_angle",
    "has_dynamic_rotation",
    "resolve_exact_initial_tangent_angle",
    "sample_path_tangent_angles",
    "unwrap_angles",
]
