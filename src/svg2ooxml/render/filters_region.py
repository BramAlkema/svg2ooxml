"""Filter region computation and colorspace conversion helpers."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from svg2ooxml.core.resvg.usvg_tree import FilterNode, FilterPrimitive
from svg2ooxml.render.surface import Surface

_GAMMA = 2.4
_INV_GAMMA = 1.0 / _GAMMA


def primitive_unit_scale(
    filter_node: FilterNode,
    bounds: tuple[float, float, float, float],
    viewport: Any,
):
    from svg2ooxml.render.filters import PrimitiveUnitScale

    min_x, min_y, max_x, max_y = bounds
    bbox_width = max(max_x - min_x, 0.0)
    bbox_height = max(max_y - min_y, 0.0)
    if bbox_width == 0.0:
        bbox_width = viewport.width / viewport.scale_x
    if bbox_height == 0.0:
        bbox_height = viewport.height / viewport.scale_y

    units = (filter_node.primitive_units or "userSpaceOnUse").strip()
    if units == "objectBoundingBox":
        scale_x = bbox_width * viewport.scale_x
        scale_y = bbox_height * viewport.scale_y
    else:
        scale_x = viewport.scale_x
        scale_y = viewport.scale_y

    return PrimitiveUnitScale(scale_x=scale_x, scale_y=scale_y, bbox_width=bbox_width, bbox_height=bbox_height)


def compute_filter_region(
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
        x_frac = parse_fraction(attrs.get("x"), -0.1)
        y_frac = parse_fraction(attrs.get("y"), -0.1)
        width_frac = parse_fraction(attrs.get("width"), 1.2)
        height_frac = parse_fraction(attrs.get("height"), 1.2)
        x = min_x + x_frac * bbox_width
        y = min_y + y_frac * bbox_height
        width = width_frac * bbox_width
        height = height_frac * bbox_height
    else:
        default_x = min_x - 0.1 * bbox_width
        default_y = min_y - 0.1 * bbox_height
        default_width = bbox_width * 1.2
        default_height = bbox_height * 1.2
        x = parse_user_length(attrs.get("x"), default_x, viewport_width)
        y = parse_user_length(attrs.get("y"), default_y, viewport_height)
        width = parse_user_length(attrs.get("width"), default_width, viewport_width)
        height = parse_user_length(attrs.get("height"), default_height, viewport_height)

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


def parse_fraction(value: str | None, default: float) -> float:
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    try:
        if value.endswith("%"):
            return float(value[:-1]) / 100.0
        return float(value)
    except ValueError:
        return default


def parse_user_length(value: str | None, default: float, viewport_length: float) -> float:
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


def apply_filter_region(surface: Surface, region: tuple[int, int, int, int], width: int, height: int) -> None:
    x0, y0, x1, y1 = region
    mask = np.zeros((height, width), dtype=bool)
    mask[y0:y1, x0:x1] = True
    surface.data[~mask] = 0.0


def resolve_color_mode(filter_node: FilterNode, primitive: FilterPrimitive) -> str:
    mode = primitive.attributes.get("color-interpolation-filters")
    if mode:
        return mode
    return filter_node.styles.get("color-interpolation-filters", "sRGB")


def convert_to_colorspace(surface: Surface, linear: bool) -> Surface:
    if not linear:
        return surface.clone()
    result = surface.clone()
    rgb = np.clip(result.data[..., :3], 0.0, 1.0)
    result.data[..., :3] = np.power(rgb, _GAMMA)
    return result


def linear_to_srgb_surface(surface: Surface) -> Surface:
    result = surface.clone()
    rgb = np.clip(result.data[..., :3], 0.0, 1.0)
    result.data[..., :3] = np.power(rgb, _INV_GAMMA)
    return result
