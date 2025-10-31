"""Filter planning and execution."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

from svg2ooxml.core.resvg.painting.paint import parse_color
from svg2ooxml.core.resvg.usvg_tree import FilterNode, FilterPrimitive
from svg2ooxml.render.surface import Surface

_GAMMA = 2.4
_INV_GAMMA = 1.0 / _GAMMA


@dataclass(slots=True)
class FilterPrimitivePlan:
    primitive: FilterPrimitive


@dataclass(slots=True)
class FilterPlan:
    filter_node: FilterNode
    primitives: List[FilterPrimitivePlan]


def plan_filter(filter_node: FilterNode) -> FilterPlan:
    primitives = [FilterPrimitivePlan(primitive=p) for p in filter_node.primitives]
    return FilterPlan(filter_node=filter_node, primitives=primitives)


def apply_filter(
    surface: Surface,
    plan: FilterPlan,
    bounds: tuple[float, float, float, float],
    viewport: Any,
) -> Surface:
    region = _compute_filter_region(plan.filter_node, bounds, viewport)

    images: Dict[str, Surface] = {
        "SourceGraphic": surface.clone(),
        "SourceAlpha": _extract_alpha(surface),
    }
    current = surface.clone()

    for primitive_plan in plan.primitives:
        primitive = primitive_plan.primitive
        tag = primitive.tag
        attrs = primitive.attributes
        styles = primitive.styles
        mode = _resolve_color_mode(plan.filter_node, primitive)
        linear = mode == "linearRGB"

        input_name = attrs.get("in")
        input_surface = images.get(input_name) if input_name else current
        if input_surface is None:
            input_surface = current

        work_input = _convert_to_colorspace(input_surface, linear)

        if tag == "feGaussianBlur":
            sigma = float(attrs.get("stdDeviation", "0") or 0)
            if sigma > 0:
                work_result = _apply_gaussian_blur(work_input, sigma)
            else:
                work_result = work_input.clone()
        elif tag == "feOffset":
            dx = float(attrs.get("dx", "0") or 0)
            dy = float(attrs.get("dy", "0") or 0)
            work_result = _apply_offset(work_input, dx, dy)
        elif tag == "feColorMatrix":
            work_result = _apply_color_matrix(work_input, attrs)
        elif tag == "feFlood":
            work_result = _apply_flood(surface.width, surface.height, attrs, styles, mode)
        elif tag == "feComposite":
            in2_name = attrs.get("in2")
            in2_surface = images.get(in2_name) if in2_name else current
            if in2_surface is None:
                in2_surface = current
            work_in2 = _convert_to_colorspace(in2_surface, linear)
            work_result = _apply_composite(work_input, work_in2, attrs.get("operator", "over"))
        else:
            work_result = work_input.clone()

        if linear:
            current = _linear_to_srgb_surface(work_result)
        else:
            current = work_result.clone()

        result_name = attrs.get("result")
        if result_name:
            images[result_name] = current.clone()
        images["_last"] = current.clone()

    _apply_filter_region(current, region, surface.width, surface.height)
    return current


def _apply_gaussian_blur(surface: Surface, sigma: float) -> Surface:
    radius = max(int(3 * sigma + 0.5), 1)
    x = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-(x**2) / (2 * sigma * sigma))
    kernel /= kernel.sum()

    data = surface.data.copy()
    pad = len(kernel) // 2
    blurred = np.empty_like(data)

    for channel in range(data.shape[2]):
        channel_data = data[..., channel]
        padded = np.pad(channel_data, ((0, 0), (pad, pad)), mode="edge")
        horiz = np.apply_along_axis(lambda row: np.convolve(row, kernel, mode="valid"), axis=1, arr=padded)
        padded = np.pad(horiz, ((pad, pad), (0, 0)), mode="edge")
        vert = np.apply_along_axis(lambda col: np.convolve(col, kernel, mode="valid"), axis=0, arr=padded)
        blurred[..., channel] = vert

    return Surface(surface.width, surface.height, blurred)


def _apply_offset(surface: Surface, dx: float, dy: float) -> Surface:
    result = Surface.make(surface.width, surface.height)
    x_shift = int(round(dx))
    y_shift = int(round(dy))

    shifted = np.roll(surface.data, shift=(y_shift, x_shift), axis=(0, 1))
    if y_shift > 0:
        shifted[:y_shift, :, :] = 0.0
    elif y_shift < 0:
        shifted[y_shift:, :, :] = 0.0
    if x_shift > 0:
        shifted[:, :x_shift, :] = 0.0
    elif x_shift < 0:
        shifted[:, x_shift:, :] = 0.0

    result.data[...] = shifted
    return result


def _extract_alpha(surface: Surface) -> Surface:
    alpha_surface = Surface.make(surface.width, surface.height)
    alpha = surface.data[..., 3:4]
    alpha_surface.data[..., 3:4] = alpha
    return alpha_surface


def _apply_color_matrix(surface: Surface, attrs: Dict[str, str]) -> Surface:
    matrix_type = attrs.get("type", "matrix")
    data = surface.data.copy()

    if matrix_type == "saturate":
        value = float(attrs.get("values", "1") or 1.0)
        value = max(0.0, min(1.0, value))
        luminance = 0.2126 * data[..., 0] + 0.7152 * data[..., 1] + 0.0722 * data[..., 2]
        data[..., 0] = luminance * (1.0 - value) + data[..., 0] * value
        data[..., 1] = luminance * (1.0 - value) + data[..., 1] * value
        data[..., 2] = luminance * (1.0 - value) + data[..., 2] * value
        return Surface(surface.width, surface.height, data)

    if matrix_type == "luminanceToAlpha":
        luminance = 0.2126 * data[..., 0] + 0.7152 * data[..., 1] + 0.0722 * data[..., 2]
        result = Surface.make(surface.width, surface.height)
        result.data[..., 3] = luminance
        return result

    values = attrs.get("values", "")
    parts = [float(part) for part in values.replace(",", " ").split() if part]
    if len(parts) != 20:
        return surface.clone()
    matrix = np.array(parts, dtype=np.float32).reshape(4, 5)
    rgba = surface.data.reshape(-1, 4)
    transformed = np.dot(rgba, matrix[:, :4].T) + matrix[:, 4]
    transformed = transformed.reshape(surface.height, surface.width, 4)
    transformed = np.clip(transformed, 0.0, 1.0)
    return Surface(surface.width, surface.height, transformed.astype(np.float32))


def _apply_flood(width: int, height: int, attrs: Dict[str, str], styles: Dict[str, str], mode: str) -> Surface:
    color_value = attrs.get("flood-color") or styles.get("flood-color") or "#000000"
    opacity_value = attrs.get("flood-opacity") or styles.get("flood-opacity")
    opacity = float(opacity_value) if opacity_value is not None and opacity_value.strip() else 1.0
    color = parse_color(color_value, opacity)
    if color is None:
        color = parse_color("#000000", opacity)
    surface = Surface.make(width, height)
    rgb = np.array([color.r, color.g, color.b], dtype=np.float32)
    if mode == "linearRGB":
        rgb = np.power(np.clip(rgb, 0.0, 1.0), _GAMMA)
    premult = rgb * color.a
    rgba = np.concatenate([premult, np.array([color.a], dtype=np.float32)])
    surface.data[...] = rgba
    return surface


def _apply_composite(a: Surface, b: Surface, operator: str) -> Surface:
    result = Surface.make(a.width, a.height)
    src = a.data
    dst = b.data
    src_rgb = src[..., :3]
    src_alpha = src[..., 3:4]
    dst_rgb = dst[..., :3]
    dst_alpha = dst[..., 3:4]

    if operator == "over":
        out_alpha = src_alpha + dst_alpha * (1.0 - src_alpha)
        out_rgb = src_rgb + dst_rgb * (1.0 - src_alpha)
    elif operator == "in":
        out_rgb = src_rgb * dst_alpha
        out_alpha = src_alpha * dst_alpha
    elif operator == "out":
        out_rgb = src_rgb * (1.0 - dst_alpha)
        out_alpha = src_alpha * (1.0 - dst_alpha)
    elif operator == "atop":
        out_rgb = src_rgb * dst_alpha + dst_rgb * (1.0 - src_alpha)
        out_alpha = dst_alpha
    elif operator == "xor":
        out_rgb = src_rgb * (1.0 - dst_alpha) + dst_rgb * (1.0 - src_alpha)
        out_alpha = src_alpha * (1.0 - dst_alpha) + dst_alpha * (1.0 - src_alpha)
    else:
        out_rgb = src_rgb
        out_alpha = src_alpha

    result.data[..., :3] = out_rgb
    result.data[..., 3:4] = out_alpha
    return result


def _compute_filter_region(
    filter_node: FilterNode,
    bounds: tuple[float, float, float, float],
    viewport,
) -> tuple[int, int, int, int]:
    min_x, min_y, max_x, max_y = bounds
    bbox_width = max(max_x - min_x, 0.0)
    bbox_height = max(max_y - min_y, 0.0)
    viewport_width = viewport.width / viewport.scale_x
    viewport_height = viewport.height / viewport.scale_y
    if bbox_width == 0.0:
        bbox_width = viewport_width
    if bbox_height == 0.0:
        bbox_height = viewport_height

    attrs = filter_node.attributes
    units = (filter_node.filter_units or "objectBoundingBox").strip()

    if units == "objectBoundingBox":
        x_frac = _parse_fraction(attrs.get("x"), -0.1)
        y_frac = _parse_fraction(attrs.get("y"), -0.1)
        width_frac = _parse_fraction(attrs.get("width"), 1.2)
        height_frac = _parse_fraction(attrs.get("height"), 1.2)
        x = min_x + x_frac * bbox_width
        y = min_y + y_frac * bbox_height
        width = width_frac * bbox_width
        height = height_frac * bbox_height
    else:
        default_x = min_x - 0.1 * bbox_width
        default_y = min_y - 0.1 * bbox_height
        default_width = bbox_width * 1.2
        default_height = bbox_height * 1.2
        x = _parse_user_length(attrs.get("x"), default_x, viewport_width)
        y = _parse_user_length(attrs.get("y"), default_y, viewport_height)
        width = _parse_user_length(attrs.get("width"), default_width, viewport_width)
        height = _parse_user_length(attrs.get("height"), default_height, viewport_height)

    if width <= 0 or height <= 0:
        return (0, 0, viewport.width, viewport.height)

    left = int(math.floor((x - viewport.min_x) * viewport.scale_x))
    top = int(math.floor((y - viewport.min_y) * viewport.scale_y))
    right = int(math.ceil((x + width - viewport.min_x) * viewport.scale_x))
    bottom = int(math.ceil((y + height - viewport.min_y) * viewport.scale_y))

    left = max(0, min(viewport.width, left))
    right = max(left, min(viewport.width, right))
    top = max(0, min(viewport.height, top))
    bottom = max(top, min(viewport.height, bottom))
    return left, top, right, bottom


def _parse_fraction(value: Optional[str], default: float) -> float:
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _parse_user_length(value: Optional[str], default: float, viewport_length: float) -> float:
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    try:
        if value.endswith("%"):
            pct = float(value[:-1])
            return (pct / 100.0) * viewport_length
        return float(value)
    except ValueError:
        return default


def _apply_filter_region(surface: Surface, region: tuple[int, int, int, int], width: int, height: int) -> None:
    x0, y0, x1, y1 = region
    mask = np.zeros((height, width), dtype=bool)
    mask[y0:y1, x0:x1] = True
    surface.data[~mask] = 0.0


def _resolve_color_mode(filter_node: FilterNode, primitive: FilterPrimitive) -> str:
    mode = primitive.attributes.get("color-interpolation-filters")
    if mode:
        return mode
    return filter_node.styles.get("color-interpolation-filters", "sRGB")


def _convert_to_colorspace(surface: Surface, linear: bool) -> Surface:
    if not linear:
        return surface.clone()
    result = surface.clone()
    rgb = np.clip(result.data[..., :3], 0.0, 1.0)
    result.data[..., :3] = np.power(rgb, _GAMMA)
    return result


def _linear_to_srgb_surface(surface: Surface) -> Surface:
    result = surface.clone()
    rgb = np.clip(result.data[..., :3], 0.0, 1.0)
    result.data[..., :3] = np.power(rgb, _INV_GAMMA)
    return result


__all__ = ["FilterPlan", "FilterPrimitivePlan", "plan_filter", "apply_filter"]
