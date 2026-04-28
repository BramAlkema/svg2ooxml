"""Sampled center-motion composition and animation grouping helpers."""

from __future__ import annotations

from typing import Any

from svg2ooxml.core.export import sampled_center_motion_parse as _parse_helpers
from svg2ooxml.core.export import sampled_center_motion_types as _motion_types
from svg2ooxml.core.export.animation_predicates import _sampled_motion_group_key
from svg2ooxml.core.export.element_translation import (
    _translate_element_to_center_target,
)
from svg2ooxml.core.export.sampled_center_motion_builder import (
    _build_sampled_center_motion_composition as _build_sampled_center_motion_composition,
)
from svg2ooxml.core.export.scene_index import _build_scene_element_index
from svg2ooxml.core.ir.converter import IRScene
from svg2ooxml.ir.animation import AnimationDefinition

AnimationMember = _motion_types.AnimationMember
_SampledCenterMotionComposition = _motion_types._SampledCenterMotionComposition
_group_transform_clone_origin = _parse_helpers._group_transform_clone_origin
_interpolate_numeric_keyframes = _parse_helpers._interpolate_numeric_keyframes
_interpolate_pair_keyframes = _parse_helpers._interpolate_pair_keyframes
_numeric_bounds = _parse_helpers._numeric_bounds
_parse_rotate_keyframes = _parse_helpers._parse_rotate_keyframes
_parse_scale_bounds = _parse_helpers._parse_scale_bounds
_parse_translate_pair = _parse_helpers._parse_translate_pair
_rotate_around_point = _parse_helpers._rotate_around_point


def _compose_sampled_center_motions(
    animations: list[AnimationDefinition],
    scene: IRScene,
) -> list[AnimationDefinition]:
    """Compose known stacked transform/motion cases into sampled center paths.

    Some SVG stacks change the shape center in ways PowerPoint cannot infer by
    simply combining independent native effects. For those cases we:

    1. move the base IR element to the authored SVG start center
    2. replace the position-changing fragments with one sampled motion path
    3. keep the editable scale/rotate effect, but suppress its naive companion
       motion because the composed path already includes that center movement
    """
    scene_index = _build_scene_element_index(scene)
    alias_map = scene_index.alias_map
    element_map = scene_index.element_map
    center_map = scene_index.center_map

    group_map: dict[tuple[Any, ...], list[AnimationMember]] = {}
    for index, animation in enumerate(animations):
        group_key = _sampled_motion_group_key(animation, alias_map)
        group_map.setdefault(group_key, []).append((index, animation))

    compositions: list[_SampledCenterMotionComposition] = []
    for members in group_map.values():
        base_animation = min(members, key=lambda item: item[0])[1]
        element = element_map.get(base_animation.element_id)
        current_center = center_map.get(base_animation.element_id)
        if element is None or current_center is None:
            continue

        composition = _build_sampled_center_motion_composition(
            element=element,
            current_center=current_center,
            members=members,
        )
        if composition is not None:
            compositions.append(composition)

    if not compositions:
        return animations

    center_targets = {
        composition.element_id: composition.start_center
        for composition in compositions
    }
    scene.elements = [
        _translate_element_to_center_target(element, center_targets)
        for element in scene.elements
    ]

    replacements = {
        composition.replacement_index: composition for composition in compositions
    }
    updated_indices: dict[int, AnimationDefinition] = {}
    consumed_indices: set[int] = set()
    for composition in compositions:
        updated_indices.update(composition.updated_indices)
        consumed_indices.update(composition.consumed_indices)

    composed: list[AnimationDefinition] = []
    for index, animation in enumerate(animations):
        if index in replacements:
            composed.append(replacements[index].replacement_animation)
        if index in consumed_indices:
            continue
        composed.append(updated_indices.get(index, animation))
    return composed


__all__ = ["_compose_sampled_center_motions"]
