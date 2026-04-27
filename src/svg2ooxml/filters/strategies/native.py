"""Native DrawingML filter rendering facade."""

from __future__ import annotations

from .native_builders import (
    build_blip_color_transform_stack_effect,
    build_component_transfer_alpha_stack_effect,
    build_flood_blur_merge_effect,
    build_lighting_composite_effect,
    build_shadow_stack_effect,
)
from .native_matchers import (
    match_color_transform_stack,
    match_flood_blur_merge_stack,
    match_lighting_composite_stack,
    match_shadow_stack,
)
from .native_render import render_color_transform_stack, render_editable_stack
from .native_utils import (
    aggregate_blip_color_transforms,
    coerce_non_negative_float,
    component_transfer_alpha_scale,
    is_additive_composite,
    parse_float_attr,
    primitive_local_name,
)

__all__ = [
    "aggregate_blip_color_transforms",
    "build_blip_color_transform_stack_effect",
    "build_component_transfer_alpha_stack_effect",
    "build_flood_blur_merge_effect",
    "build_lighting_composite_effect",
    "build_shadow_stack_effect",
    "coerce_non_negative_float",
    "component_transfer_alpha_scale",
    "is_additive_composite",
    "match_color_transform_stack",
    "match_flood_blur_merge_stack",
    "match_lighting_composite_stack",
    "match_shadow_stack",
    "parse_float_attr",
    "primitive_local_name",
    "render_color_transform_stack",
    "render_editable_stack",
]
