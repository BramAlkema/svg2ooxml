"""Projection and PowerPoint path formatting for motion paths."""

from __future__ import annotations

from typing import TYPE_CHECKING

from svg2ooxml.drawingml.animation.handlers.motion_path_types import PointPair

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition


def project_motion_points(
    points: list[PointPair],
    animation: AnimationDefinition,
) -> list[PointPair]:
    """Project SVG motion points into absolute slide-space shape positions."""

    if not points:
        return points

    matrix = animation.motion_space_matrix
    if matrix is None:
        transformed = list(points)
    else:
        a, b, c, d, e, f = matrix
        transformed = [(a * x + c * y + e, b * x + d * y + f) for x, y in points]

    offset_x = 0.0
    offset_y = 0.0
    if animation.element_motion_offset_px is not None:
        offset_x, offset_y = animation.element_motion_offset_px

    if abs(offset_x) < 1e-9 and abs(offset_y) < 1e-9:
        return transformed
    return [(x + offset_x, y + offset_y) for x, y in transformed]


def build_motion_path_string(
    points: list[PointPair],
    animation: AnimationDefinition,
) -> str:
    """Convert absolute slide-space points to a PowerPoint motion path."""

    viewport_w = 960.0
    viewport_h = 720.0
    if animation.motion_viewport_px is not None:
        viewport_w = max(animation.motion_viewport_px[0], 1.0)
        viewport_h = max(animation.motion_viewport_px[1], 1.0)
    start_x, start_y = points[0]

    segments: list[str] = []
    for index, (x_px, y_px) in enumerate(points):
        dx_px = x_px - start_x
        dy_px = y_px - start_y
        nx = dx_px / viewport_w
        ny = dy_px / viewport_h
        cmd = "M" if index == 0 else "L"
        segments.append(f"{cmd} {format_coord(nx)} {format_coord(ny)}")

    return " ".join(segments) + " E"


def format_coord(value: float) -> str:
    """Format normalized coordinate as a compact string."""

    if abs(value) < 1e-10:
        return "0"
    return f"{value:.6g}"


__all__ = [
    "build_motion_path_string",
    "format_coord",
    "project_motion_points",
]
