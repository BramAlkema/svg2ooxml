"""DrawingML effect builders for native filter strategy matches."""

from __future__ import annotations

import copy
import math
from typing import Any

from lxml import etree

from svg2ooxml.common.conversions.angles import radians_to_ppt
from svg2ooxml.common.conversions.opacity import opacity_to_ppt
from svg2ooxml.common.units import px_to_emu
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.primitives.flood import FloodFilter
from svg2ooxml.filters.primitives.gaussian_blur import GaussianBlurFilter
from svg2ooxml.filters.primitives.lighting import (
    DiffuseLightingFilter,
    SpecularLightingFilter,
)
from svg2ooxml.filters.primitives.offset import OffsetFilter
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.services.filter_types import FilterEffectResult

from .native_utils import (
    aggregate_blip_color_transforms,
    coerce_non_negative_float,
    parse_float_attr,
    primitive_local_name,
)


def build_flood_blur_merge_effect(
    context: FilterContext,
    flood_primitive: etree._Element,
    blur_primitive: etree._Element,
    merge_inputs: list[str],
) -> FilterEffectResult | None:
    """Build a native glow effect from a flood+blur+merge stack."""
    flood_filter = FloodFilter()
    blur_filter = GaussianBlurFilter()
    flood_params = flood_filter._parse_params(flood_primitive)
    blur_params = blur_filter._parse_params(blur_primitive, context)

    radius_scale = blur_filter._resolve_radius_scale(
        blur_filter._primitive_policy(context.policy),
        False,
    )
    base_radius_px = max(blur_params.std_dev_x, blur_params.std_dev_y) * radius_scale
    if base_radius_px <= 0 or flood_params.opacity <= 0:
        return None

    effective_radius_px = base_radius_px
    alpha = flood_params.opacity
    policy_meta: dict[str, float] = {}

    max_glow_radius = coerce_non_negative_float(context.policy.get("max_glow_radius"))
    if max_glow_radius is not None:
        policy_meta["max_glow_radius"] = max_glow_radius
        if effective_radius_px > max_glow_radius:
            effective_radius_px = max_glow_radius

    max_glow_alpha = coerce_non_negative_float(context.policy.get("max_glow_alpha"))
    if max_glow_alpha is not None:
        clamped_alpha = min(max_glow_alpha, 1.0)
        policy_meta["max_glow_alpha"] = clamped_alpha
        if alpha > clamped_alpha:
            alpha = clamped_alpha

    radius_emu = int(px_to_emu(effective_radius_px))
    effect_lst = a_elem("effectLst")
    glow = a_sub(effect_lst, "glow", rad=radius_emu)
    srgb = a_sub(glow, "srgbClr", val=flood_params.color)
    a_sub(srgb, "alpha", val=opacity_to_ppt(alpha))

    metadata: dict[str, Any] = {
        "filter_type": "filter_stack",
        "stack_type": "flood_blur_merge",
        "approximation": "glow",
        "editable_stack": True,
        "native_support": True,
        "mimic_strategy": "glow",
        "source_primitives": ["feFlood", "feGaussianBlur", "feMerge"],
        "merge_inputs": merge_inputs,
        "flood_color": flood_params.color,
        "flood_opacity": flood_params.opacity,
        "glow_color": flood_params.color,
        "alpha": alpha,
        "std_deviation_x": blur_params.std_dev_x,
        "std_deviation_y": blur_params.std_dev_y,
        "is_isotropic": blur_params.is_isotropic,
        "radius_scale": radius_scale,
        "radius_px": base_radius_px,
        "radius_effective": effective_radius_px,
        "radius_emu": radius_emu,
    }
    if effective_radius_px < base_radius_px:
        metadata["clamped_radius"] = effective_radius_px
    if alpha < flood_params.opacity:
        metadata["alpha_clamped"] = True
    if policy_meta:
        metadata["policy"] = policy_meta

    return FilterEffectResult(
        effect=CustomEffect(drawingml=to_string(effect_lst)),
        strategy="native",
        metadata=metadata,
        fallback=None,
    )


def build_shadow_stack_effect(
    context: FilterContext,
    offset_primitive: etree._Element,
    blur_primitive: etree._Element,
    flood_primitive: etree._Element,
    merge_inputs: list[str],
) -> FilterEffectResult:
    """Build a native outer-shadow effect from the matched stack."""
    offset_filter = OffsetFilter()
    blur_filter = GaussianBlurFilter()
    flood_filter = FloodFilter()

    offset_params = offset_filter._parse_params(offset_primitive, context)
    blur_params = blur_filter._parse_params(blur_primitive, context)
    flood_params = flood_filter._parse_params(flood_primitive)

    radius_scale = blur_filter._resolve_radius_scale(
        blur_filter._primitive_policy(context.policy),
        False,
    )
    base_radius_px = max(blur_params.std_dev_x, blur_params.std_dev_y) * radius_scale
    distance_px = math.hypot(offset_params.dx, offset_params.dy)
    if base_radius_px <= 0 or flood_params.opacity <= 0:
        return FilterEffectResult(
            effect=CustomEffect(drawingml=to_string(a_elem("effectLst"))),
            strategy="native",
            metadata={
                "filter_type": "filter_stack",
                "stack_type": "offset_blur_flood_composite_merge",
                "native_support": False,
                "fallback_reason": "non_positive_radius_or_alpha",
            },
            fallback="bitmap",
        )

    effective_distance_px = distance_px
    policy_meta: dict[str, float] = {}
    max_shadow_distance = coerce_non_negative_float(context.policy.get("max_shadow_distance"))
    if max_shadow_distance is not None:
        policy_meta["max_shadow_distance"] = max_shadow_distance
        if effective_distance_px > max_shadow_distance:
            effective_distance_px = max_shadow_distance

    distance_scale = effective_distance_px / distance_px if distance_px > 1e-6 else 0.0
    effective_dx = offset_params.dx * distance_scale
    effective_dy = offset_params.dy * distance_scale

    blur_radius_emu = int(px_to_emu(base_radius_px))
    distance_emu = int(px_to_emu(effective_distance_px))
    direction = 0
    if distance_emu > 0:
        direction = radians_to_ppt(math.atan2(effective_dy, effective_dx) % (2 * math.pi))

    effect_lst = a_elem("effectLst")
    shadow = a_sub(
        effect_lst,
        "outerShdw",
        blurRad=blur_radius_emu,
        dist=distance_emu,
        dir=direction,
        algn="ctr",
        rotWithShape="0",
    )
    srgb = a_sub(shadow, "srgbClr", val=flood_params.color)
    a_sub(srgb, "alpha", val=opacity_to_ppt(flood_params.opacity))

    metadata: dict[str, Any] = {
        "filter_type": "filter_stack",
        "stack_type": "offset_blur_flood_composite_merge",
        "approximation": "outer_shadow",
        "editable_stack": True,
        "native_support": True,
        "mimic_strategy": "outer_shadow",
        "source_primitives": [
            "feOffset",
            "feGaussianBlur",
            "feFlood",
            "feComposite",
            "feMerge",
        ],
        "merge_inputs": merge_inputs,
        "flood_color": flood_params.color,
        "flood_opacity": flood_params.opacity,
        "alpha": flood_params.opacity,
        "dx": offset_params.dx,
        "dy": offset_params.dy,
        "dx_effective": effective_dx,
        "dy_effective": effective_dy,
        "distance_px": distance_px,
        "distance_effective": effective_distance_px,
        "distance_emu": distance_emu,
        "direction": direction,
        "std_deviation_x": blur_params.std_dev_x,
        "std_deviation_y": blur_params.std_dev_y,
        "is_isotropic": blur_params.is_isotropic,
        "radius_scale": radius_scale,
        "radius_px": base_radius_px,
        "radius_effective": base_radius_px,
        "radius_emu": blur_radius_emu,
    }
    if effective_distance_px < distance_px:
        metadata["distance_clamped"] = True
    if policy_meta:
        metadata["policy"] = policy_meta

    return FilterEffectResult(
        effect=CustomEffect(drawingml=to_string(effect_lst)),
        strategy="native",
        metadata=metadata,
        fallback=None,
    )


def build_lighting_composite_effect(
    context: FilterContext,
    lighting_primitive: etree._Element,
    composite_primitive: etree._Element,
) -> FilterEffectResult | None:
    """Build a native lighting composite effect."""
    lighting_tag = primitive_local_name(lighting_primitive)
    lighting_filter = (
        DiffuseLightingFilter() if lighting_tag == "fediffuselighting" else SpecularLightingFilter()
    )
    lighting_result = lighting_filter.apply(copy.deepcopy(lighting_primitive), context)
    fragment = (lighting_result.drawingml or "").strip()
    if lighting_result.fallback is not None or not fragment:
        return None

    metadata = dict(lighting_result.metadata or {})
    base_filter_type = metadata.get("filter_type")
    metadata.update(
        {
            "filter_type": "filter_stack",
            "lighting_filter_type": base_filter_type,
            "stack_type": (
                "diffuse_lighting_composite"
                if lighting_tag == "fediffuselighting"
                else "specular_lighting_composite"
            ),
            "editable_stack": True,
            "native_support": True,
            "source_primitives": [
                "feDiffuseLighting" if lighting_tag == "fediffuselighting" else "feSpecularLighting",
                "feComposite",
            ],
            "composite_operator": "arithmetic",
            "composite_coefficients": {
                "k1": parse_float_attr(composite_primitive.get("k1")),
                "k2": parse_float_attr(composite_primitive.get("k2")),
                "k3": parse_float_attr(composite_primitive.get("k3")),
                "k4": parse_float_attr(composite_primitive.get("k4")),
            },
        }
    )
    return FilterEffectResult(
        effect=CustomEffect(drawingml=fragment),
        strategy="native",
        metadata=metadata,
        fallback=None,
    )


def build_component_transfer_alpha_stack_effect(
    steps: list[dict[str, Any]],
) -> FilterEffectResult:
    """Build an effectDag alpha-mod-fix from component-transfer alpha steps."""
    alpha_scales = [
        float(step["alpha_scale"])
        for step in steps
        if isinstance(step.get("alpha_scale"), (int, float))
    ]
    total_alpha = 1.0
    for scale in alpha_scales:
        total_alpha *= scale
    alpha_amt = max(0, min(int(round(total_alpha * 100000)), 200000))

    effect_dag = a_elem("effectDag")
    a_sub(effect_dag, "cont")
    alpha_mod_fix = a_sub(effect_dag, "alphaModFix", amt=alpha_amt)
    a_sub(alpha_mod_fix, "cont")

    metadata: dict[str, Any] = {
        "filter_type": "filter_stack",
        "stack_type": "component_transfer_alpha_stack",
        "approximation": "alpha_mod_fix",
        "editable_stack": True,
        "terminal_stack": True,
        "native_support": True,
        "mimic_strategy": "effect_dag_alpha_mod_fix",
        "source_primitives": [str(step["tag"]) for step in steps],
        "alpha_scale_steps": alpha_scales,
        "alpha_scale_total": total_alpha,
        "alpha_mod_amount": alpha_amt,
    }

    return FilterEffectResult(
        effect=CustomEffect(drawingml=to_string(effect_dag)),
        strategy="native",
        metadata=metadata,
        fallback=None,
    )


def build_blip_color_transform_stack_effect(
    steps: list[dict[str, Any]],
    context: FilterContext,
    drawingml_renderer: Any,
) -> list[FilterEffectResult]:
    """Build blip color-transform stack effect via the DrawingML renderer."""
    aggregated_transforms = aggregate_blip_color_transforms(
        [
            transform
            for step in steps
            for transform in (step.get("blip_color_transforms") or [])
            if isinstance(transform, dict)
        ]
    )
    if not aggregated_transforms:
        return []

    fallback = "emf"
    if any(
        (step.get("result") and getattr(step["result"], "fallback", None) in {"bitmap", "raster"})
        for step in steps
    ):
        fallback = "bitmap"

    primary_filter_type = (
        "color_matrix"
        if any(step.get("tag") == "feColorMatrix" for step in steps)
        else "component_transfer"
    )
    metadata: dict[str, Any] = {
        "filter_type": primary_filter_type,
        "stack_filter_type": "filter_stack",
        "stack_type": "color_transform_blip_stack",
        "approximation": "blip_color_transforms",
        "mimic_strategy": "blip_color_transforms",
        "editable_stack": False,
        "terminal_stack": True,
        "native_support": False,
        "source_primitives": [str(step["tag"]) for step in steps],
        "native_color_transform_context": "blip",
        "blip_color_transforms": aggregated_transforms,
    }
    filter_result = FilterResult(
        success=True,
        drawingml="",
        fallback=fallback,
        metadata=metadata,
    )
    return drawingml_renderer.render([filter_result], context=context)
