"""Rendering orchestration for editable native filter stacks."""

from __future__ import annotations

import copy
from typing import Any

from lxml import etree

from svg2ooxml.filters.base import FilterContext
from svg2ooxml.filters.primitives.color_matrix import ColorMatrixFilter
from svg2ooxml.filters.primitives.component_transfer import ComponentTransferFilter
from svg2ooxml.services.filter_types import FilterEffectResult

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
from .native_utils import component_transfer_alpha_scale, primitive_local_name


def render_editable_stack(
    element: etree._Element,
    context: FilterContext,
    drawingml_renderer: Any,
) -> list[FilterEffectResult]:
    """Try to match and render an editable native stack from *element*."""
    color_transform_stack = render_color_transform_stack(element, context, drawingml_renderer)
    if color_transform_stack:
        return color_transform_stack

    if not bool(context.policy.get("approximation_allowed", True)):
        return []

    glow_match = match_flood_blur_merge_stack(element)
    if glow_match is not None:
        flood_primitive, blur_primitive, merge_inputs = glow_match
        glow_effect = build_flood_blur_merge_effect(
            context,
            flood_primitive,
            blur_primitive,
            merge_inputs,
        )
        if glow_effect is not None:
            return [glow_effect]

    shadow_match = match_shadow_stack(element)
    if shadow_match is not None:
        offset_primitive, blur_primitive, flood_primitive, merge_inputs = shadow_match
        return [
            build_shadow_stack_effect(
                context,
                offset_primitive,
                blur_primitive,
                flood_primitive,
                merge_inputs,
            )
        ]

    lighting_match = match_lighting_composite_stack(element)
    if lighting_match is not None:
        lighting_primitive, composite_primitive = lighting_match
        lighting_effect = build_lighting_composite_effect(
            context,
            lighting_primitive,
            composite_primitive,
        )
        if lighting_effect is not None:
            return [lighting_effect]

    return []


def render_color_transform_stack(
    element: etree._Element,
    context: FilterContext,
    drawingml_renderer: Any,
) -> list[FilterEffectResult]:
    """Attempt native rendering of a colour-transform stack."""
    primitives = match_color_transform_stack(element)
    if primitives is None:
        return []

    enable_effect_dag = bool(context.policy.get("enable_effect_dag", False))
    enable_native_color_transforms = bool(
        context.policy.get("enable_native_color_transforms", False)
    )
    enable_blip_effect_enrichment = bool(
        context.policy.get("enable_blip_effect_enrichment", False)
    )
    if not enable_effect_dag and not (
        enable_native_color_transforms and enable_blip_effect_enrichment
    ):
        return []

    steps: list[dict[str, Any]] = []
    all_alpha_component_transfer = True
    for primitive in primitives:
        local_tag = primitive_local_name(primitive)
        if local_tag == "fecomponenttransfer":
            transfer_filter = ComponentTransferFilter()
            transfer_result = transfer_filter.apply(copy.deepcopy(primitive), context)
            functions = transfer_filter._parse_functions(primitive)
            alpha_scale = component_transfer_alpha_scale(
                transfer_filter,
                functions,
            )
            steps.append(
                {
                    "tag": "feComponentTransfer",
                    "result": transfer_result,
                    "alpha_scale": alpha_scale,
                    "blip_color_transforms": list(
                        transfer_result.metadata.get("blip_color_transforms") or []
                    ),
                }
            )
            if alpha_scale is None:
                all_alpha_component_transfer = False
        elif local_tag == "fecolormatrix":
            matrix_filter = ColorMatrixFilter()
            matrix_result = matrix_filter.apply(copy.deepcopy(primitive), context)
            blip_color_transforms = list(
                matrix_result.metadata.get("blip_color_transforms") or []
            )
            if not blip_color_transforms:
                return []
            steps.append(
                {
                    "tag": "feColorMatrix",
                    "result": matrix_result,
                    "blip_color_transforms": blip_color_transforms,
                }
            )
            all_alpha_component_transfer = False
        else:
            return []

    if enable_effect_dag and all_alpha_component_transfer and steps:
        return [build_component_transfer_alpha_stack_effect(steps)]

    if not (enable_native_color_transforms and enable_blip_effect_enrichment):
        return []

    return build_blip_color_transform_stack_effect(steps, context, drawingml_renderer)
