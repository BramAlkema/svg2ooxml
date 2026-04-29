"""Execution loop for planned SVG filters."""

from __future__ import annotations

from typing import Any

from svg2ooxml.common.units.lengths import parse_number
from svg2ooxml.render import filters_lighting as _lighting
from svg2ooxml.render import filters_ops as _ops
from svg2ooxml.render import filters_region as _region
from svg2ooxml.render.filters_model import (
    ComponentTransferPlan,
    FilterPlan,
    UnsupportedPrimitiveError,
)
from svg2ooxml.render.surface import Surface


def apply_filter(
    surface: Surface,
    plan: FilterPlan,
    bounds: tuple[float, float, float, float],
    viewport: Any,
) -> Surface:
    region = _region.compute_filter_region(plan.filter_node, bounds, viewport)
    unit_scale = _region.primitive_unit_scale(plan.filter_node, bounds, viewport)

    images: dict[str, Surface] = {
        "SourceGraphic": surface.clone(),
        "SourceAlpha": _ops.extract_alpha(surface),
    }
    current = surface.clone()

    for primitive_plan in plan.primitives:
        primitive = primitive_plan.primitive
        tag_lower = primitive_plan.tag.lower()
        linear = primitive_plan.color_mode == "linearRGB"

        if tag_lower == "feflood":
            work_result = _ops.apply_flood(
                surface.width,
                surface.height,
                primitive.attributes,
                primitive.styles,
                primitive_plan.color_mode,
            )
        elif tag_lower == "feturbulence":
            work_result = _ops.apply_turbulence(
                surface.width,
                surface.height,
                primitive_plan.extra,
                unit_scale,
                linear,
            )
        elif tag_lower == "feimage":
            image_info = primitive_plan.extra.get("image")
            if image_info is None:
                raise UnsupportedPrimitiveError(primitive_plan.tag, "missing decoded image data", primitive=primitive)
            image_surface: Surface = image_info["surface"].clone()
            work_input = _region.convert_to_colorspace(image_surface, linear)
            work_result = _ops.place_image_surface(work_input, surface.width, surface.height)
        else:
            inputs = _ops.resolve_inputs(images, primitive_plan.inputs, current, linear)
            primary = inputs[0] if inputs else _region.convert_to_colorspace(current, linear)
            if tag_lower == "fegaussianblur":
                sigma_x, sigma_y = primitive_plan.extra.get("std_deviation", (0.0, 0.0))
                sigma_x *= unit_scale.scale_x
                sigma_y *= unit_scale.scale_y
                work_result = _ops.apply_gaussian_blur(primary, sigma_x, sigma_y)
            elif tag_lower == "feoffset":
                dx = primitive_plan.extra.get("dx", 0.0) * unit_scale.scale_x
                dy = primitive_plan.extra.get("dy", 0.0) * unit_scale.scale_y
                work_result = _ops.apply_offset(primary, dx, dy)
            elif tag_lower == "fecolormatrix":
                work_result = _ops.apply_color_matrix(primary, primitive.attributes)
            elif tag_lower == "fecomposite":
                if len(inputs) < 2:
                    raise UnsupportedPrimitiveError(primitive_plan.tag, "feComposite requires two inputs", primitive=primitive)
                operator = primitive_plan.extra.get("operator", "over")
                work_result = _ops.apply_composite(
                    primary,
                    inputs[1],
                    operator,
                    k1=parse_number(primitive_plan.extra.get("k1"), 0.0),
                    k2=parse_number(primitive_plan.extra.get("k2"), 0.0),
                    k3=parse_number(primitive_plan.extra.get("k3"), 0.0),
                    k4=parse_number(primitive_plan.extra.get("k4"), 0.0),
                )
            elif tag_lower == "feblend":
                if len(inputs) < 2:
                    raise UnsupportedPrimitiveError(primitive_plan.tag, "feBlend requires two inputs", primitive=primitive)
                mode = primitive_plan.extra.get("mode")
                work_result = _ops.apply_blend(primary, inputs[1], mode, linear)
            elif tag_lower == "fediffuselighting":
                work_result = _lighting.apply_diffuse_lighting(
                    primary,
                    primitive_plan.extra,
                    unit_scale,
                )
            elif tag_lower == "fespecularlighting":
                work_result = _lighting.apply_specular_lighting(
                    primary,
                    primitive_plan.extra,
                    unit_scale,
                )
            elif tag_lower == "fedisplacementmap":
                if len(inputs) < 2:
                    raise UnsupportedPrimitiveError(
                        primitive_plan.tag, "feDisplacementMap requires two inputs", primitive=primitive
                    )
                work_result = _lighting.apply_displacement_map(
                    primary,
                    inputs[1],
                    primitive_plan.extra.get("scale", 0.0),
                    primitive_plan.extra.get("x_channel", "A"),
                    primitive_plan.extra.get("y_channel", "A"),
                    unit_scale,
                )
            elif tag_lower == "femerge":
                work_result = _ops.apply_merge(inputs)
            elif tag_lower == "fecomponenttransfer":
                functions = primitive_plan.extra.get("functions")
                if not isinstance(functions, ComponentTransferPlan):
                    raise UnsupportedPrimitiveError(primitive_plan.tag, "component transfer plan missing", primitive=primitive)
                work_result = _ops.apply_component_transfer(primary, functions)
            elif tag_lower == "femorphology":
                operator = primitive_plan.extra.get("operator", "erode")
                radius_x = primitive_plan.extra.get("radius_x", 0.0) * unit_scale.scale_x
                radius_y = primitive_plan.extra.get("radius_y", 0.0) * unit_scale.scale_y
                work_result = _ops.apply_morphology(primary, operator, radius_x, radius_y)
            elif tag_lower == "fetile":
                work_result = primary.clone()
            else:  # pragma: no cover - defensive
                work_result = primary.clone()

        if linear:
            current = _region.linear_to_srgb_surface(work_result)
        else:
            current = work_result.clone()

        result_name = primitive_plan.result_name
        if result_name:
            images[result_name] = current.clone()
        images["_last"] = current.clone()

    _region.apply_filter_region(current, region, surface.width, surface.height)
    return current


__all__ = ["apply_filter"]
