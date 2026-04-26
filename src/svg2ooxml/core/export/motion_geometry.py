"""Affine, rotation, and heading utilities for animation motion."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from svg2ooxml.core.export.element_translation import _translate_element_to_motion_start
from svg2ooxml.core.ir.converter import IRScene
from svg2ooxml.ir.animation import AnimationDefinition, AnimationType

# ---------------------------------------------------------------------------
# Sampling & interpolation
# ---------------------------------------------------------------------------


def _sample_progress_values(steps: int = 12) -> list[float]:
    return [step / steps for step in range(steps + 1)]


def _lerp(start: float, end: float, progress: float) -> float:
    return start + (end - start) * progress


# ---------------------------------------------------------------------------
# Affine matrix helpers
# ---------------------------------------------------------------------------


def _resolve_affine_matrix(
    animations: Sequence[AnimationDefinition],
) -> tuple[float, float, float, float, float, float] | None:
    for animation in animations:
        if animation.motion_space_matrix is not None:
            return animation.motion_space_matrix
    return None


def _project_affine_point(
    point: tuple[float, float],
    matrix: tuple[float, float, float, float, float, float] | None,
) -> tuple[float, float]:
    x, y = point
    if matrix is None:
        return (x, y)
    a, b, c, d, e, f = matrix
    return (a * x + c * y + e, b * x + d * y + f)


def _inverse_project_affine_point(
    point: tuple[float, float],
    matrix: tuple[float, float, float, float, float, float] | None,
) -> tuple[float, float]:
    x, y = point
    if matrix is None:
        return (x, y)
    a, b, c, d, e, f = matrix
    det = (a * d) - (b * c)
    if abs(det) <= 1e-9:
        return (x, y)
    px = x - e
    py = y - f
    return ((d * px - c * py) / det, (-b * px + a * py) / det)


def _inverse_project_affine_rect(
    rect: Any,
    matrix: tuple[float, float, float, float, float, float] | None,
):
    from svg2ooxml.ir.geometry import Rect

    corners = (
        (float(rect.x), float(rect.y)),
        (float(rect.x + rect.width), float(rect.y)),
        (float(rect.x), float(rect.y + rect.height)),
        (float(rect.x + rect.width), float(rect.y + rect.height)),
    )
    local_corners = [_inverse_project_affine_point(corner, matrix) for corner in corners]
    xs = [corner[0] for corner in local_corners]
    ys = [corner[1] for corner in local_corners]
    return Rect(
        min(xs),
        min(ys),
        max(xs) - min(xs),
        max(ys) - min(ys),
    )


def _image_local_layout(
    element: Any,
    local_bbox: Any,
):
    from svg2ooxml.ir.geometry import Rect

    metadata = getattr(element, "metadata", None)
    if not isinstance(metadata, dict):
        return local_bbox, local_bbox
    layout = metadata.get("image_layout")
    if not isinstance(layout, dict):
        return local_bbox, local_bbox

    viewport = layout.get("viewport")
    content_offset = layout.get("content_offset")
    content_size = layout.get("content_size")
    if not (
        isinstance(viewport, dict)
        and isinstance(content_offset, dict)
        and isinstance(content_size, dict)
    ):
        return local_bbox, local_bbox

    try:
        viewport_rect = Rect(
            float(viewport["x"]),
            float(viewport["y"]),
            float(viewport["width"]),
            float(viewport["height"]),
        )
        content_rect = Rect(
            viewport_rect.x + float(content_offset["x"]),
            viewport_rect.y + float(content_offset["y"]),
            float(content_size["width"]),
            float(content_size["height"]),
        )
    except (KeyError, TypeError, ValueError):
        return local_bbox, local_bbox

    return viewport_rect, content_rect


# ---------------------------------------------------------------------------
# Rotation & projection
# ---------------------------------------------------------------------------


def _rotate_point(point: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    radians = math.radians(angle_deg)
    cos_v = math.cos(radians)
    sin_v = math.sin(radians)
    x, y = point
    return (x * cos_v - y * sin_v, x * sin_v + y * cos_v)


def _project_linear_motion_delta(
    dx: float,
    dy: float,
    animation: AnimationDefinition,
) -> tuple[float, float]:
    matrix = animation.motion_space_matrix
    if matrix is None:
        return (dx, dy)
    a, b, c, d, _e, _f = matrix
    return (a * dx + c * dy, b * dx + d * dy)


# ---------------------------------------------------------------------------
# Element heading inference
# ---------------------------------------------------------------------------


def _infer_element_heading_deg(element: Any) -> float | None:
    from svg2ooxml.ir.geometry import LineSegment
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Line, Polygon, Polyline

    if isinstance(element, Line):
        dx = element.end.x - element.start.x
        dy = element.end.y - element.start.y
        if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
            return None
        return _angle_deg(dx, dy)

    if isinstance(element, Polyline):
        return _infer_heading_from_points(
            [(point.x, point.y) for point in element.points],
            closed=False,
        )

    if isinstance(element, Polygon):
        return _infer_heading_from_points(
            [(point.x, point.y) for point in element.points],
            closed=True,
        )

    if isinstance(element, IRPath):
        points: list[tuple[float, float]] = []
        for segment in element.segments:
            start = getattr(segment, "start", None)
            end = getattr(segment, "end", None)
            if start is not None:
                points.append((float(start.x), float(start.y)))
            if isinstance(segment, LineSegment) and end is not None:
                points.append((float(end.x), float(end.y)))
        return _infer_heading_from_points(points, closed=element.is_closed)

    return None


def _infer_heading_from_points(
    points: list[tuple[float, float]],
    *,
    closed: bool,
) -> float | None:
    vertices = _dedupe_motion_vertices(points, closed=closed)
    if len(vertices) < 2:
        return None

    if closed and len(vertices) >= 3:
        centroid_x = sum(x for x, _y in vertices) / len(vertices)
        centroid_y = sum(y for _x, y in vertices) / len(vertices)
        ranked = sorted(
            (
                ((x - centroid_x) ** 2 + (y - centroid_y) ** 2, x, y)
                for x, y in vertices
            ),
            reverse=True,
        )
        if ranked[0][0] > 1e-6:
            if len(ranked) == 1 or ranked[0][0] - ranked[1][0] > ranked[0][0] * 0.05:
                _distance_sq, tip_x, tip_y = ranked[0]
                return _angle_deg(tip_x - centroid_x, tip_y - centroid_y)

    start_x, start_y = vertices[0]
    end_x, end_y = vertices[-1]
    dx = end_x - start_x
    dy = end_y - start_y
    if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
        return None
    return _angle_deg(dx, dy)


def _dedupe_motion_vertices(
    points: list[tuple[float, float]],
    *,
    closed: bool,
) -> list[tuple[float, float]]:
    deduped: list[tuple[float, float]] = []
    for x, y in points:
        if not deduped or abs(deduped[-1][0] - x) > 1e-6 or abs(deduped[-1][1] - y) > 1e-6:
            deduped.append((x, y))
    if (
        closed
        and len(deduped) > 1
        and abs(deduped[0][0] - deduped[-1][0]) <= 1e-6
        and abs(deduped[0][1] - deduped[-1][1]) <= 1e-6
    ):
        deduped.pop()
    return deduped


def _angle_deg(dx: float, dy: float) -> float:
    return float(math.degrees(math.atan2(dy, dx)))


# ---------------------------------------------------------------------------
# Motion start extraction & projection
# ---------------------------------------------------------------------------


def _first_motion_point(
    animation: AnimationDefinition,
) -> tuple[float, float] | None:
    from svg2ooxml.common.geometry.paths import PathParseError
    from svg2ooxml.common.geometry.paths.motion import parse_motion_path_data

    if not animation.values:
        return None

    path_value = animation.values[0].strip()
    if not path_value:
        return None

    try:
        segments = parse_motion_path_data(path_value)
    except PathParseError:
        return None

    if segments:
        start = getattr(segments[0], "start", None)
        if start is not None:
            return (float(start.x), float(start.y))

    return None


def _project_motion_point(
    point: tuple[float, float],
    animation: AnimationDefinition,
) -> tuple[float, float]:
    x, y = point
    if animation.motion_space_matrix is not None:
        a, b, c, d, e, f = animation.motion_space_matrix
        x, y = (a * x + c * y + e, b * x + d * y + f)

    if animation.element_motion_offset_px is not None:
        offset_x, offset_y = animation.element_motion_offset_px
        x += offset_x
        y += offset_y

    return (x, y)


# ---------------------------------------------------------------------------
# Immediate motion start application
# ---------------------------------------------------------------------------


def _apply_immediate_motion_starts(
    scene: IRScene,
    animations: list[AnimationDefinition],
) -> None:
    """Pre-position begin=0 motion targets at their SVG path start points."""
    start_positions: dict[str, tuple[float, float]] = {}
    for animation in animations:
        if animation.animation_type != AnimationType.ANIMATE_MOTION:
            continue
        if (
            animation.target_attribute == "position"
            and animation.motion_space_matrix is None
            and animation.element_motion_offset_px is None
        ):
            # Synthesized relative delta paths already start from the authored
            # base geometry in the scene. Re-applying a motion-start probe
            # would incorrectly snap those shapes to (0, 0).
            continue
        if abs(animation.timing.begin) > 1e-9:
            continue
        first_point = _first_motion_point(animation)
        if first_point is None:
            continue
        start_positions[animation.element_id] = _project_motion_point(first_point, animation)

    if not start_positions:
        return

    scene.elements = [
        _translate_element_to_motion_start(element, start_positions)
        for element in scene.elements
    ]
