"""Native DrawingML filter rendering — editable stacks and pattern matching."""

from __future__ import annotations

import copy
import math
from typing import Any

from lxml import etree

from svg2ooxml.common.conversions.angles import radians_to_ppt
from svg2ooxml.common.conversions.opacity import opacity_to_ppt
from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.common.units import px_to_emu
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.primitives.color_matrix import ColorMatrixFilter
from svg2ooxml.filters.primitives.component_transfer import ComponentTransferFilter
from svg2ooxml.filters.primitives.flood import FloodFilter
from svg2ooxml.filters.primitives.gaussian_blur import GaussianBlurFilter
from svg2ooxml.filters.primitives.lighting import (
    DiffuseLightingFilter,
    SpecularLightingFilter,
)
from svg2ooxml.filters.primitives.merge import MergeFilter
from svg2ooxml.filters.primitives.offset import OffsetFilter
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.services.filter_types import FilterEffectResult

# ---------------------------------------------------------------------------
# Stack matching helpers
# ---------------------------------------------------------------------------


def match_flood_blur_merge_stack(
    element: etree._Element,
) -> tuple[etree._Element, etree._Element, list[str]] | None:
    """Detect feFlood -> feGaussianBlur -> feMerge glow pattern."""
    primitives = [child for child in element if hasattr(child, "tag")]
    if len(primitives) != 3:
        return None

    tags = [primitive_local_name(child) for child in primitives]
    if tags != ["feflood", "fegaussianblur", "femerge"]:
        return None

    flood_primitive, blur_primitive, merge_primitive = primitives
    merge_inputs = MergeFilter()._parse_params(merge_primitive).inputs
    if "SourceGraphic" not in merge_inputs:
        return None

    blur_result = (blur_primitive.get("result") or "").strip()
    if not blur_result:
        return None

    non_source_inputs = [
        token for token in merge_inputs if token not in {"SourceGraphic", "SourceAlpha"}
    ]
    if non_source_inputs != [blur_result]:
        return None

    blur_input = (blur_primitive.get("in") or "").strip()
    flood_result = (flood_primitive.get("result") or "").strip()
    if blur_input and (not flood_result or blur_input != flood_result):
        return None

    return flood_primitive, blur_primitive, merge_inputs


def match_shadow_stack(
    element: etree._Element,
) -> tuple[etree._Element, etree._Element, etree._Element, list[str]] | None:
    """Detect feOffset->feGaussianBlur->feFlood->feComposite->feMerge shadow pattern."""
    primitives = [child for child in element if hasattr(child, "tag")]
    if len(primitives) != 5:
        return None

    tags = [primitive_local_name(child) for child in primitives]
    if tags != ["feoffset", "fegaussianblur", "feflood", "fecomposite", "femerge"]:
        return None

    offset_primitive, blur_primitive, flood_primitive, composite_primitive, merge_primitive = primitives
    composite_operator = (composite_primitive.get("operator") or "over").strip().lower()
    if composite_operator != "in":
        return None

    offset_input = (offset_primitive.get("in") or "SourceAlpha").strip()
    if offset_input not in {"SourceAlpha", "SourceGraphic"}:
        return None

    offset_result = (offset_primitive.get("result") or "").strip()
    blur_input = (blur_primitive.get("in") or "").strip()
    if not offset_result or blur_input != offset_result:
        return None

    blur_result = (blur_primitive.get("result") or "").strip()
    flood_result = (flood_primitive.get("result") or "").strip()
    composite_input_1 = (composite_primitive.get("in") or "").strip()
    composite_input_2 = (composite_primitive.get("in2") or "").strip()
    if not blur_result or not flood_result:
        return None
    if composite_input_1 != flood_result or composite_input_2 != blur_result:
        return None

    composite_result = (composite_primitive.get("result") or "").strip()
    if not composite_result:
        return None

    merge_inputs = MergeFilter()._parse_params(merge_primitive).inputs
    if "SourceGraphic" not in merge_inputs:
        return None

    non_source_inputs = [
        token for token in merge_inputs if token not in {"SourceGraphic", "SourceAlpha"}
    ]
    if non_source_inputs != [composite_result]:
        return None

    return offset_primitive, blur_primitive, flood_primitive, merge_inputs


def match_lighting_composite_stack(
    element: etree._Element,
) -> tuple[etree._Element, etree._Element] | None:
    """Detect feDiffuseLighting/feSpecularLighting + feComposite(arithmetic) pattern."""
    primitives = [child for child in element if hasattr(child, "tag")]
    if len(primitives) != 2:
        return None

    lighting_primitive, composite_primitive = primitives
    lighting_tag = primitive_local_name(lighting_primitive)
    composite_tag = primitive_local_name(composite_primitive)
    if lighting_tag not in {"fediffuselighting", "fespecularlighting"}:
        return None
    if composite_tag != "fecomposite":
        return None

    operator = (composite_primitive.get("operator") or "over").strip().lower()
    if operator != "arithmetic":
        return None

    coefficients = (
        parse_float_attr(composite_primitive.get("k1")),
        parse_float_attr(composite_primitive.get("k2")),
        parse_float_attr(composite_primitive.get("k3")),
        parse_float_attr(composite_primitive.get("k4")),
    )
    if not is_additive_composite(*coefficients):
        return None

    lighting_result_name = (lighting_primitive.get("result") or "").strip()
    if not lighting_result_name:
        return None

    composite_in = (composite_primitive.get("in") or "").strip()
    composite_in2 = (composite_primitive.get("in2") or "").strip()
    inputs = {composite_in, composite_in2}
    if inputs != {lighting_result_name, "SourceGraphic"}:
        return None

    return lighting_primitive, composite_primitive


def match_color_transform_stack(
    element: etree._Element,
) -> list[etree._Element] | None:
    """Match a chain of feColorMatrix/feComponentTransfer primitives."""
    primitives = [child for child in element if hasattr(child, "tag")]
    if len(primitives) < 2:
        return None

    previous_result_name: str | None = None
    for index, primitive in enumerate(primitives):
        local_tag = primitive_local_name(primitive)
        if local_tag not in {"fecolormatrix", "fecomponenttransfer"}:
            return None

        input_name = (primitive.get("in") or "").strip()
        if index == 0:
            if input_name and input_name not in {"SourceGraphic", "SourceAlpha"}:
                return None
        elif input_name and input_name != previous_result_name:
            return None

        previous_result_name = (primitive.get("result") or "").strip() or previous_result_name

    return primitives


# ---------------------------------------------------------------------------
# Effect builders
# ---------------------------------------------------------------------------


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

    distance_scale = (
        effective_distance_px / distance_px
        if distance_px > 1e-6
        else 0.0
    )
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


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------


def primitive_local_name(primitive: etree._Element) -> str:
    return local_name(getattr(primitive, "tag", None)).lower()


def component_transfer_alpha_scale(
    transfer_filter: ComponentTransferFilter,
    functions: list[Any],
) -> float | None:
    alpha_scale: float | None = None
    for function in functions:
        channel = getattr(function, "channel", "")
        if channel == "a":
            if getattr(function, "func_type", "") == "identity":
                continue
            params = getattr(function, "params", {}) or {}
            if getattr(function, "func_type", "") != "linear":
                return None
            try:
                intercept = float(params.get("intercept", 0.0))
                slope = float(params.get("slope", 1.0))
            except (TypeError, ValueError):
                return None
            if abs(intercept) > 1e-6:
                return None
            alpha_scale = slope
            continue

        if not transfer_filter._is_identity_function(function):
            return None

    return alpha_scale


def aggregate_blip_color_transforms(
    transforms: list[dict[str, object]],
) -> list[dict[str, object]]:
    aggregated: list[dict[str, object]] = []
    seen_order: list[str] = []
    alpha_mod_fix = 1.0
    sat_mod = 1.0
    hue_off = 0
    passthrough: list[dict[str, object]] = []

    for transform in transforms:
        tag = transform.get("tag")
        if not isinstance(tag, str):
            continue
        if tag not in seen_order:
            seen_order.append(tag)
        if tag == "alphaModFix":
            try:
                alpha_mod_fix *= float(transform.get("amt", 100000)) / 100000.0
            except (TypeError, ValueError):
                continue
        elif tag == "satMod":
            try:
                sat_mod *= float(transform.get("val", 100000)) / 100000.0
            except (TypeError, ValueError):
                continue
        elif tag == "hueOff":
            try:
                hue_off += int(round(float(transform.get("val", 0))))
            except (TypeError, ValueError):
                continue
        else:
            passthrough.append(dict(transform))

    for tag in seen_order:
        if tag == "alphaModFix":
            amt = max(0, min(int(round(alpha_mod_fix * 100000)), 200000))
            if amt != 100000:
                aggregated.append({"tag": "alphaModFix", "amt": amt})
        elif tag == "satMod":
            val = max(0, min(int(round(sat_mod * 100000)), 400000))
            if val != 100000:
                aggregated.append({"tag": "satMod", "val": val})
        elif tag == "hueOff":
            val = hue_off % 21600000
            if val:
                aggregated.append({"tag": "hueOff", "val": val})

    aggregated.extend(passthrough)
    return aggregated


def coerce_non_negative_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        coerced = float(value)
    elif isinstance(value, str):
        try:
            coerced = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    if coerced < 0:
        return None
    return coerced


def parse_float_attr(value: str | None) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def is_additive_composite(k1: float, k2: float, k3: float, k4: float) -> bool:
    tolerance = 1e-6
    return (
        abs(k1) <= tolerance
        and abs(k2 - 1.0) <= tolerance
        and abs(k3 - 1.0) <= tolerance
        and abs(k4) <= tolerance
    )
