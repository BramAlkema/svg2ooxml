"""Lighting and displacement filter primitives."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np

from svg2ooxml.render.surface import Surface

_EPSILON = 1e-6


def apply_diffuse_lighting(
    surface: Surface,
    params: Mapping[str, Any],
    units,
) -> Surface:
    light = params.get("light", {})
    color = np.array(params.get("lighting_color", (1.0, 1.0, 1.0)), dtype=np.float32)
    surface_scale = float(params.get("surface_scale", 1.0))
    diffuse_constant = float(params.get("constant", 1.0))
    kernel_length = params.get("kernel_length", (1.0, 1.0))

    height_map = height_map_from_surface(surface) * surface_scale
    spacing_x = float(kernel_length[0]) if kernel_length else 1.0
    spacing_y = float(kernel_length[1]) if kernel_length else 1.0
    spacing_x = max(spacing_x, _EPSILON) * (units.scale_x or 1.0)
    spacing_y = max(spacing_y, _EPSILON) * (units.scale_y or 1.0)

    grad_y, grad_x = np.gradient(height_map, spacing_y, spacing_x, edge_order=1)
    normal = np.stack((-grad_x, -grad_y, np.ones_like(height_map)), axis=-1)
    norm = np.linalg.norm(normal, axis=-1, keepdims=True)
    normal = normal / np.maximum(norm, _EPSILON)

    light_vec, light_weight = light_direction(light, surface.shape[1], surface.shape[0], units, height_map)
    dot = np.maximum(0.0, np.sum(normal * light_vec, axis=-1)) * light_weight

    source_alpha = np.clip(surface.data[..., 3], 0.0, 1.0)
    intensity = diffuse_constant * dot * source_alpha
    rgb = np.clip(intensity[..., None] * color, 0.0, 1.0)
    alpha = np.clip(intensity, 0.0, 1.0)

    result = Surface.make(surface.width, surface.height)
    result.data[..., :3] = rgb * alpha[..., None]
    result.data[..., 3] = alpha
    return result


def apply_specular_lighting(
    surface: Surface,
    params: Mapping[str, Any],
    units,
) -> Surface:
    light = params.get("light", {})
    light_type = params.get("light_type")
    color = np.array(params.get("lighting_color", (1.0, 1.0, 1.0)), dtype=np.float32)
    surface_scale = float(params.get("surface_scale", 1.0))
    specular_constant = float(params.get("constant", 1.0))
    specular_exponent = float(params.get("exponent", 1.0))
    kernel_length = params.get("kernel_length", (1.0, 1.0))

    height_map = height_map_from_surface(surface) * surface_scale
    spacing_x = float(kernel_length[0]) if kernel_length else 1.0
    spacing_y = float(kernel_length[1]) if kernel_length else 1.0
    spacing_x = max(spacing_x, _EPSILON) * (units.scale_x or 1.0)
    spacing_y = max(spacing_y, _EPSILON) * (units.scale_y or 1.0)

    grad_y, grad_x = np.gradient(height_map, spacing_y, spacing_x, edge_order=1)
    normal = np.stack((-grad_x, -grad_y, np.ones_like(height_map)), axis=-1)
    norm = np.linalg.norm(normal, axis=-1, keepdims=True)
    normal = normal / np.maximum(norm, _EPSILON)

    light_vec, light_weight = light_direction(light, surface.shape[1], surface.shape[0], units, height_map)
    view = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    view = view / np.linalg.norm(view)

    dot_nl = np.maximum(0.0, np.sum(normal * light_vec, axis=-1, keepdims=True))
    reflection = 2.0 * dot_nl * normal - light_vec
    reflection_norm = np.linalg.norm(reflection, axis=-1, keepdims=True)
    reflection = reflection / np.maximum(reflection_norm, _EPSILON)

    spec_amount = np.maximum(
        0.0, reflection[..., 0] * view[0] + reflection[..., 1] * view[1] + reflection[..., 2] * view[2]
    )
    source_alpha = np.clip(surface.data[..., 3], 0.0, 1.0)
    intensity = specular_constant * np.power(spec_amount, specular_exponent)
    if light_type == "spot":
        intensity *= light_weight
    intensity *= light_weight
    intensity *= source_alpha
    intensity = np.clip(intensity, 0.0, 1.0)

    rgb = color * intensity[..., None]
    result = Surface.make(surface.width, surface.height)
    result.data[..., :3] = rgb
    result.data[..., 3] = intensity.astype(np.float32)
    result.data[..., :3] *= result.data[..., 3:4]
    return result


def height_map_from_surface(surface: Surface) -> np.ndarray:
    alpha = np.clip(surface.data[..., 3], 0.0, 1.0)
    rgb = surface.data[..., :3]
    safe_alpha = np.maximum(alpha, _EPSILON)
    unpremult = np.zeros_like(rgb)
    mask = alpha > _EPSILON
    if np.any(mask):
        unpremult[mask] = rgb[mask] / safe_alpha[mask, None]
    luminance = (
        0.2126 * unpremult[..., 0]
        + 0.7152 * unpremult[..., 1]
        + 0.0722 * unpremult[..., 2]
    )
    # fall back to alpha when no colour is present
    height_map = np.where(mask, luminance, alpha)
    return np.clip(height_map, 0.0, 1.0).astype(np.float32)


def light_direction(
    light: Mapping[str, Any],
    width: int,
    height: int,
    units,
    height_map: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if not light:
        direction = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        vec = np.broadcast_to(direction, (height, width, 3)).copy()
        weights = np.ones((height, width), dtype=np.float32)
        return vec, weights

    scale_x = units.scale_x if units.scale_x else 1.0
    scale_y = units.scale_y if units.scale_y else 1.0
    user_x = (np.arange(width, dtype=np.float32) + 0.5) / max(scale_x, _EPSILON)
    user_y = (np.arange(height, dtype=np.float32) + 0.5) / max(scale_y, _EPSILON)
    grid_x, grid_y = np.meshgrid(user_x, user_y)

    if light.get("type") == "distant":
        direction = np.array(light.get("direction", (0.0, 0.0, 1.0)), dtype=np.float32)
        norm = np.linalg.norm(direction)
        if norm <= _EPSILON:
            direction = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        else:
            direction = direction / norm
        vec = np.broadcast_to(direction, (height, width, 3)).copy()
        weight = np.ones((height, width), dtype=np.float32)
        return vec, weight

    light_pos = np.array(
        [
            float(light.get("x", 0.0)),
            float(light.get("y", 0.0)),
            float(light.get("z", 0.0)),
        ],
        dtype=np.float32,
    )
    surface_pos = np.stack([grid_x, grid_y, height_map], axis=-1)

    to_light = light_pos - surface_pos
    norm = np.linalg.norm(to_light, axis=-1, keepdims=True)
    direction = to_light / np.maximum(norm, _EPSILON)
    weight = np.ones((height, width), dtype=np.float32)

    if light.get("type") == "spot":
        axis = np.array(
            [
                float(light.get("points_at_x", 0.0)) - light_pos[0],
                float(light.get("points_at_y", 0.0)) - light_pos[1],
                float(light.get("points_at_z", 0.0)) - light_pos[2],
            ],
            dtype=np.float32,
        )
        axis_norm = np.linalg.norm(axis)
        if axis_norm <= _EPSILON:
            axis = np.array([0.0, 0.0, -1.0], dtype=np.float32)
        else:
            axis = axis / axis_norm
        to_point = surface_pos - light_pos
        to_point_unit = to_point / np.maximum(np.linalg.norm(to_point, axis=-1, keepdims=True), _EPSILON)
        cos_angle = np.clip(np.sum(to_point_unit * axis, axis=-1), -1.0, 1.0)
        limiting = light.get("limiting_cone")
        if limiting is not None:
            mask = cos_angle >= math.cos(limiting)
            weight = np.where(mask, 1.0, 0.0)
        cone_exp = float(light.get("cone_exponent", 1.0))
        weight *= np.power(np.clip(cos_angle, 0.0, 1.0), cone_exp)

    return direction.astype(np.float32), weight.astype(np.float32)


def apply_displacement_map(
    source: Surface,
    displacement: Surface,
    scale: float,
    x_channel: str,
    y_channel: str,
    units,
) -> Surface:
    if scale == 0.0:
        return source.clone()

    disp_data = displacement.data
    alpha = np.clip(disp_data[..., 3], 0.0, 1.0)
    denom = np.maximum(alpha, _EPSILON)[..., None]
    unpremult = np.where(alpha[..., None] > _EPSILON, disp_data[..., :3] / denom, 0.0)

    def _channel(value: str) -> np.ndarray:
        if value == "A":
            return alpha
        index = {"R": 0, "G": 1, "B": 2}.get(value, 0)
        return unpremult[..., index]

    x_values = _channel(x_channel)
    y_values = _channel(y_channel)

    scale_x = float(scale) * units.scale_x
    scale_y = float(scale) * units.scale_y

    dx = (x_values * 2.0 - 1.0) * scale_x
    dy = (y_values * 2.0 - 1.0) * scale_y

    height, width = source.height, source.width
    grid_x, grid_y = np.meshgrid(
        np.arange(width, dtype=np.float32),
        np.arange(height, dtype=np.float32),
    )
    sample_x = grid_x + dx.astype(np.float32)
    sample_y = grid_y + dy.astype(np.float32)

    sampled = bilinear_sample(source.data, sample_x, sample_y)
    return Surface(width, height, sampled.astype(np.float32))


def bilinear_sample(data: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    height, width = data.shape[:2]
    xs = np.clip(xs, 0.0, width - 1.0)
    ys = np.clip(ys, 0.0, height - 1.0)

    x0 = np.floor(xs).astype(np.int32)
    y0 = np.floor(ys).astype(np.int32)
    x1 = np.clip(x0 + 1, 0, width - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)

    wx = (xs - x0).astype(np.float32)[..., None]
    wy = (ys - y0).astype(np.float32)[..., None]

    top_left = data[y0, x0]
    top_right = data[y0, x1]
    bottom_left = data[y1, x0]
    bottom_right = data[y1, x1]

    top = top_left * (1.0 - wx) + top_right * wx
    bottom = bottom_left * (1.0 - wx) + bottom_right * wx
    return top * (1.0 - wy) + bottom * wy
