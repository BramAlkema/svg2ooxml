"""Coalescing of simple x/y position animations into motion paths."""

from __future__ import annotations

from dataclasses import replace as _replace
from typing import Any

from svg2ooxml.core.export.animation_predicates import _simple_position_axis
from svg2ooxml.core.export.animation_values import animation_length_delta_px
from svg2ooxml.core.export.motion_geometry import _project_linear_motion_delta
from svg2ooxml.core.export.scene_index import _build_element_alias_map
from svg2ooxml.core.export.variant_grouping import _animation_group_key
from svg2ooxml.core.export.variant_motion_shared import (
    _apply_index_replacements,
    _motion_delta_path,
)
from svg2ooxml.core.ir.converter import IRScene
from svg2ooxml.ir.animation import AnimationDefinition, AnimationType, CalcMode


def _coalesce_simple_position_motions(
    animations: list[AnimationDefinition],
    scene: IRScene,
) -> list[AnimationDefinition]:
    """Merge simple x/y animations into one motion path per rendered shape."""

    alias_map = _build_element_alias_map(scene)
    group_map: dict[tuple[Any, ...], list[tuple[int, str, AnimationDefinition]]] = {}
    for index, animation in enumerate(animations):
        axis = _simple_position_axis(animation)
        if axis is None:
            continue

        group_key = _animation_group_key(animation, alias_map)
        group_map.setdefault(group_key, []).append((index, axis, animation))

    replacements: dict[int, tuple[list[AnimationDefinition], set[int]]] = {}
    for members in group_map.values():
        replacement = _build_position_replacement(animations, members)
        if replacement is not None:
            replacements[min(replacement[1])] = replacement

    return _apply_index_replacements(animations, replacements)


def _build_position_replacement(
    animations: list[AnimationDefinition],
    members: list[tuple[int, str, AnimationDefinition]],
) -> tuple[list[AnimationDefinition], set[int]] | None:
    x_members = [member for member in members if member[1] == "x"]
    y_members = [member for member in members if member[1] == "y"]
    if len(x_members) != 1 or len(y_members) != 1:
        return None

    first_index = min(x_members[0][0], y_members[0][0])
    base_animation = animations[first_index]
    x_animation = x_members[0][2]
    y_animation = y_members[0][2]

    dx = animation_length_delta_px(x_animation, axis="x")
    dy = animation_length_delta_px(y_animation, axis="y")
    if dx is None or dy is None:
        return None
    dx, dy = _project_linear_motion_delta(dx, dy, base_animation)

    replacement = _replace(
        base_animation,
        animation_type=AnimationType.ANIMATE_MOTION,
        target_attribute="position",
        values=[_motion_delta_path(dx, dy)],
        key_times=None,
        key_splines=None,
        calc_mode=CalcMode.LINEAR,
        transform_type=None,
        motion_rotate=None,
        element_motion_offset_px=None,
        motion_space_matrix=None,
        motion_viewport_px=(
            base_animation.motion_viewport_px
            or x_animation.motion_viewport_px
            or y_animation.motion_viewport_px
        ),
    )
    return ([replacement], {x_members[0][0], y_members[0][0]})


__all__ = ["_coalesce_simple_position_motions"]
