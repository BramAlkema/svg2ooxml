"""Composition of simple line endpoint animations into motion/scale fragments."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace as _replace
from typing import Any

from svg2ooxml.core.export.animation_predicates import (
    _is_simple_line_endpoint_animation,
    _simple_position_axis,
)
from svg2ooxml.core.export.motion_geometry import _project_linear_motion_delta
from svg2ooxml.core.export.scene_index import (
    _build_element_alias_map,
    _iter_scene_elements,
    _scene_element_ids,
)
from svg2ooxml.core.export.variant_grouping import _animation_group_key
from svg2ooxml.core.export.variant_motion_shared import (
    AnimationReplacement,
    _apply_index_replacements,
    _motion_delta_path,
)
from svg2ooxml.core.ir.converter import IRScene
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationType,
    CalcMode,
    TransformType,
)
from svg2ooxml.ir.geometry import LineSegment
from svg2ooxml.ir.scene import Path as IRPath
from svg2ooxml.ir.shapes import Line

LinePoints = tuple[tuple[float, float], tuple[float, float]]
AnimationMember = tuple[int, str, AnimationDefinition]


def _compose_simple_line_endpoint_animations(
    animations: list[AnimationDefinition],
    scene: IRScene,
) -> list[AnimationDefinition]:
    """Compose simple line endpoint changes into motion + scale fragments."""

    alias_map = _build_element_alias_map(scene)
    line_points_map = _collect_line_points(scene)
    group_map = _group_endpoint_candidates(animations, alias_map)

    replacements: dict[int, AnimationReplacement] = {}
    for members in group_map.values():
        replacement = _build_endpoint_replacement(members, line_points_map)
        if replacement is not None:
            replacements[min(replacement[1])] = replacement

    return _apply_index_replacements(animations, replacements)


def _collect_line_points(scene: IRScene) -> dict[str, LinePoints]:
    line_points_map: dict[str, LinePoints] = {}
    for element in _iter_scene_elements(scene.elements):
        element_ids = _scene_element_ids(element)
        if not element_ids:
            continue
        line_points = _resolve_line_points(element)
        if line_points is None:
            continue
        for element_id in element_ids:
            line_points_map[element_id] = line_points
    return line_points_map


def _resolve_line_points(element: object) -> LinePoints | None:
    if isinstance(element, Line):
        return (
            (float(element.start.x), float(element.start.y)),
            (float(element.end.x), float(element.end.y)),
        )

    if isinstance(element, IRPath):
        line_segments = [
            segment
            for segment in element.segments
            if isinstance(segment, LineSegment)
        ]
        if len(line_segments) != 1:
            return None
        segment = line_segments[0]
        return (
            (float(segment.start.x), float(segment.start.y)),
            (float(segment.end.x), float(segment.end.y)),
        )

    return None


def _group_endpoint_candidates(
    animations: Sequence[AnimationDefinition],
    alias_map: dict[str, tuple[str, ...]],
) -> dict[tuple[Any, ...], list[AnimationMember]]:
    group_map: dict[tuple[Any, ...], list[AnimationMember]] = {}
    for index, animation in enumerate(animations):
        if animation.animation_type != AnimationType.ANIMATE:
            continue
        if animation.transform_type is not None:
            continue
        attr = animation.target_attribute
        if attr in {"x1", "x2", "y1", "y2"}:
            if not _is_simple_line_endpoint_animation(animation):
                continue
        elif _simple_position_axis(animation) is None:
            continue
        group_key = _animation_group_key(animation, alias_map)
        group_map.setdefault(group_key, []).append((index, attr, animation))
    return group_map


def _build_endpoint_replacement(
    members: Sequence[AnimationMember],
    line_points_map: dict[str, LinePoints],
) -> AnimationReplacement | None:
    endpoint_members = [
        member for member in members if member[1] in {"x1", "x2", "y1", "y2"}
    ]
    if not endpoint_members:
        return None

    base_animation = min(members, key=lambda member: member[0])[2]
    line_points = line_points_map.get(base_animation.element_id)
    if line_points is None:
        return None

    attr_to_member = _unique_endpoint_members(endpoint_members)
    if attr_to_member is None:
        return None

    x_members = [member for member in members if _simple_position_axis(member[2]) == "x"]
    y_members = [member for member in members if _simple_position_axis(member[2]) == "y"]
    if len(x_members) > 1 or len(y_members) > 1:
        return None

    deltas = _resolve_endpoint_deltas(attr_to_member)
    if deltas is None:
        return None
    dx1, dx2, dy1, dy2 = deltas

    world_delta = _resolve_world_delta(x_members, y_members)
    if world_delta is None:
        return None
    world_dx, world_dy = world_delta

    geometry = _compute_line_endpoint_geometry(line_points, dx1, dx2, dy1, dy2)
    if geometry is None:
        return None
    local_dx, local_dy, scale_x, scale_y = geometry

    matrix_source = (
        x_members[0][2]
        if x_members
        else (y_members[0][2] if y_members else base_animation)
    )
    total_dx, total_dy = _project_linear_motion_delta(
        world_dx + local_dx,
        world_dy + local_dy,
        matrix_source,
    )

    if (
        abs(total_dx) <= 1e-6
        and abs(total_dy) <= 1e-6
        and abs(scale_x - 1.0) <= 1e-6
        and abs(scale_y - 1.0) <= 1e-6
    ):
        return None

    consumed = {member[0] for member in endpoint_members}
    if x_members:
        consumed.add(x_members[0][0])
    if y_members:
        consumed.add(y_members[0][0])

    viewport = _replacement_viewport(base_animation, x_members, y_members)
    replacement_group = _build_replacement_group(
        base_animation=base_animation,
        total_dx=total_dx,
        total_dy=total_dy,
        scale_x=scale_x,
        scale_y=scale_y,
        viewport=viewport,
    )
    if not replacement_group:
        return None
    return (replacement_group, consumed)


def _unique_endpoint_members(
    endpoint_members: Sequence[AnimationMember],
) -> dict[str, tuple[int, AnimationDefinition]] | None:
    attr_to_member: dict[str, tuple[int, AnimationDefinition]] = {}
    for index, attr, animation in endpoint_members:
        if attr in attr_to_member:
            return None
        attr_to_member[attr] = (index, animation)
    return attr_to_member


def _resolve_endpoint_deltas(
    attr_to_member: dict[str, tuple[int, AnimationDefinition]],
) -> tuple[float, float, float, float] | None:
    def _delta_for(attr_name: str) -> float:
        member = attr_to_member.get(attr_name)
        if member is None:
            return 0.0
        return float(member[1].values[-1]) - float(member[1].values[0])

    try:
        return (
            _delta_for("x1"),
            _delta_for("x2"),
            _delta_for("y1"),
            _delta_for("y2"),
        )
    except (TypeError, ValueError):
        return None


def _resolve_world_delta(
    x_members: Sequence[AnimationMember],
    y_members: Sequence[AnimationMember],
) -> tuple[float, float] | None:
    try:
        world_dx = (
            float(x_members[0][2].values[-1]) - float(x_members[0][2].values[0])
            if x_members
            else 0.0
        )
        world_dy = (
            float(y_members[0][2].values[-1]) - float(y_members[0][2].values[0])
            if y_members
            else 0.0
        )
    except (TypeError, ValueError):
        return None
    return world_dx, world_dy


def _compute_line_endpoint_geometry(
    line_points: LinePoints,
    dx1: float,
    dx2: float,
    dy1: float,
    dy2: float,
) -> tuple[float, float, float, float] | None:
    (x1_start, y1_start), (x2_start, y2_start) = line_points
    x1_end = x1_start + dx1
    y1_end = y1_start + dy1
    x2_end = x2_start + dx2
    y2_end = y2_start + dy2

    start_width = abs(x1_start - x2_start)
    start_height = abs(y1_start - y2_start)
    end_width = abs(x1_end - x2_end)
    end_height = abs(y1_end - y2_end)

    if _line_orientation_flips(
        x1_start - x2_start,
        x1_end - x2_end,
        y1_start - y2_start,
        y1_end - y2_end,
    ):
        return None
    if (start_width <= 1e-6 and end_width > 1e-6) or (
        start_height <= 1e-6 and end_height > 1e-6
    ):
        return None

    scale_x = end_width / start_width if start_width > 1e-6 else 1.0
    scale_y = end_height / start_height if start_height > 1e-6 else 1.0
    return ((dx1 + dx2) / 2.0, (dy1 + dy2) / 2.0, scale_x, scale_y)


def _line_orientation_flips(
    start_dx_sign: float,
    end_dx_sign: float,
    start_dy_sign: float,
    end_dy_sign: float,
) -> bool:
    return (
        abs(start_dx_sign) > 1e-6
        and abs(end_dx_sign) > 1e-6
        and start_dx_sign * end_dx_sign < 0
    ) or (
        abs(start_dy_sign) > 1e-6
        and abs(end_dy_sign) > 1e-6
        and start_dy_sign * end_dy_sign < 0
    )


def _replacement_viewport(
    base_animation: AnimationDefinition,
    x_members: Sequence[AnimationMember],
    y_members: Sequence[AnimationMember],
) -> tuple[float, float] | None:
    viewport = base_animation.motion_viewport_px
    if viewport is None and x_members:
        viewport = x_members[0][2].motion_viewport_px
    if viewport is None and y_members:
        viewport = y_members[0][2].motion_viewport_px
    return viewport


def _build_replacement_group(
    *,
    base_animation: AnimationDefinition,
    total_dx: float,
    total_dy: float,
    scale_x: float,
    scale_y: float,
    viewport: tuple[float, float] | None,
) -> list[AnimationDefinition]:
    replacement_group: list[AnimationDefinition] = []
    if abs(total_dx) > 1e-6 or abs(total_dy) > 1e-6:
        replacement_group.append(
            _replace(
                base_animation,
                animation_type=AnimationType.ANIMATE_MOTION,
                target_attribute="position",
                values=[_motion_delta_path(total_dx, total_dy)],
                key_times=None,
                key_splines=None,
                calc_mode=CalcMode.LINEAR,
                transform_type=None,
                additive="replace",
                accumulate="none",
                motion_rotate=None,
                element_motion_offset_px=None,
                motion_space_matrix=None,
                motion_viewport_px=viewport,
            )
        )

    if abs(scale_x - 1.0) > 1e-6 or abs(scale_y - 1.0) > 1e-6:
        replacement_group.append(
            _replace(
                base_animation,
                animation_type=AnimationType.ANIMATE_TRANSFORM,
                target_attribute="transform",
                values=["1 1", f"{scale_x:.6g} {scale_y:.6g}"],
                key_times=None,
                key_splines=None,
                calc_mode=CalcMode.LINEAR,
                transform_type=TransformType.SCALE,
                additive="replace",
                accumulate="none",
                motion_rotate=None,
                element_motion_offset_px=None,
                motion_space_matrix=None,
                motion_viewport_px=viewport,
            )
        )

    return replacement_group


__all__ = ["_compose_simple_line_endpoint_animations"]
