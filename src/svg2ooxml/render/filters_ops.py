"""Pixel operations used by SVG filter execution."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from svg2ooxml.common.conversions.opacity import parse_opacity
from svg2ooxml.common.numpy_compat import require_numpy
from svg2ooxml.common.units.lengths import (
    parse_number,
    parse_number_list,
    parse_number_or_percent,
)
from svg2ooxml.core.resvg.painting.paint import parse_color
from svg2ooxml.render import filters_lighting as _lighting
from svg2ooxml.render import filters_region as _region
from svg2ooxml.render.filters_model import (
    ComponentTransferFunction,
    ComponentTransferPlan,
    PrimitiveUnitScale,
    UnsupportedPrimitiveError,
)
from svg2ooxml.render.surface import Surface

np = require_numpy("svg2ooxml.render requires NumPy; install the 'render' extra.")

_GAMMA = 2.4


def resolve_inputs(
    images: Mapping[str, Surface],
    names: Sequence[str | None],
    current: Surface,
    linear: bool,
) -> list[Surface]:
    resolved: list[Surface] = []
    for name in names:
        input_surface = _resolve_input_surface(images, name, current)
        resolved.append(_region.convert_to_colorspace(input_surface, linear))
    return resolved


def apply_gaussian_blur(surface: Surface, sigma_x: float, sigma_y: float) -> Surface:
    if sigma_x <= 0.0 and sigma_y <= 0.0:
        return surface.clone()

    data = surface.data.copy()
    result = data

    if sigma_x > 0.0:
        kernel_x = _gaussian_kernel(sigma_x)
        pad_x = len(kernel_x) // 2
        temp = np.empty_like(result)
        for channel in range(result.shape[2]):
            channel_data = result[..., channel]
            padded = np.pad(channel_data, ((0, 0), (pad_x, pad_x)), mode="edge")
            temp[..., channel] = np.apply_along_axis(
                lambda row: np.convolve(row, kernel_x, mode="valid"),
                axis=1,
                arr=padded,
            )
        result = temp

    if sigma_y > 0.0:
        kernel_y = _gaussian_kernel(sigma_y)
        pad_y = len(kernel_y) // 2
        temp = np.empty_like(result)
        for channel in range(result.shape[2]):
            channel_data = result[..., channel]
            padded = np.pad(channel_data, ((pad_y, pad_y), (0, 0)), mode="edge")
            temp[..., channel] = np.apply_along_axis(
                lambda col: np.convolve(col, kernel_y, mode="valid"),
                axis=0,
                arr=padded,
            )
        result = temp

    return Surface(surface.width, surface.height, result)


def apply_offset(surface: Surface, dx: float, dy: float) -> Surface:
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


def extract_alpha(surface: Surface) -> Surface:
    alpha_surface = Surface.make(surface.width, surface.height)
    alpha = surface.data[..., 3:4]
    alpha_surface.data[..., 3:4] = alpha
    return alpha_surface


def apply_color_matrix(surface: Surface, attrs: Mapping[str, str]) -> Surface:
    matrix_type = attrs.get("type", "matrix")
    data = surface.data.copy()

    if matrix_type == "saturate":
        value = parse_number_or_percent(attrs.get("values"), 1.0)
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
    parts = parse_number_list(values)
    if len(parts) != 20:
        return surface.clone()
    matrix = np.array(parts, dtype=np.float32).reshape(4, 5)
    rgba = surface.data.reshape(-1, 4)
    transformed = np.dot(rgba, matrix[:, :4].T) + matrix[:, 4]
    transformed = transformed.reshape(surface.height, surface.width, 4)
    transformed = np.clip(transformed, 0.0, 1.0)
    return Surface(surface.width, surface.height, transformed.astype(np.float32))


def apply_component_transfer(surface: Surface, plan: ComponentTransferPlan) -> Surface:
    data = surface.data.copy()
    alpha = np.clip(data[..., 3], 0.0, 1.0)
    safe_alpha = np.maximum(alpha, _lighting._EPSILON)

    unpremult = np.zeros_like(data[..., :3])
    mask = alpha > _lighting._EPSILON
    if np.any(mask):
        unpremult[mask] = data[..., :3][mask] / safe_alpha[mask, None]

    red = _apply_transfer_function(unpremult[..., 0], plan.red)
    green = _apply_transfer_function(unpremult[..., 1], plan.green)
    blue = _apply_transfer_function(unpremult[..., 2], plan.blue)
    out_alpha = np.clip(_apply_transfer_function(alpha, plan.alpha), 0.0, 1.0)

    out_rgb = np.stack([red, green, blue], axis=-1)
    out_rgb = np.clip(out_rgb, 0.0, 1.0)
    premult_rgb = out_rgb * out_alpha[..., None]

    result = Surface.make(surface.width, surface.height)
    result.data[..., :3] = premult_rgb.astype(np.float32)
    result.data[..., 3] = out_alpha.astype(np.float32)
    return result


def apply_morphology(surface: Surface, operator: str, radius_x: float, radius_y: float) -> Surface:
    rx = max(int(round(radius_x)), 0)
    ry = max(int(round(radius_y)), 0)
    if rx == 0 and ry == 0:
        return surface.clone()

    alpha = surface.data[..., 3]
    dilate = operator == "dilate"
    morphed_alpha = _morph_channel(alpha, rx, ry, dilate)
    morphed_alpha = np.clip(morphed_alpha, 0.0, 1.0)

    result = Surface.make(surface.width, surface.height)
    safe_alpha = np.maximum(surface.data[..., 3], _lighting._EPSILON)
    unpremult = np.zeros_like(surface.data[..., :3])
    mask = surface.data[..., 3] > _lighting._EPSILON
    if np.any(mask):
        unpremult[mask] = surface.data[..., :3][mask] / safe_alpha[mask, None]
    premult_rgb = np.clip(unpremult, 0.0, 1.0) * morphed_alpha[..., None]
    result.data[..., :3] = premult_rgb.astype(np.float32)
    result.data[..., 3] = morphed_alpha.astype(np.float32)
    return result


def apply_merge(inputs: Sequence[Surface]) -> Surface:
    if not inputs:
        raise UnsupportedPrimitiveError("feMerge", "no merge inputs available")
    result = inputs[0].clone()
    for layer in inputs[1:]:
        result.blend(layer)
    return result


def apply_turbulence(
    width: int,
    height: int,
    params: Mapping[str, Any],
    units: PrimitiveUnitScale,
    linear: bool,
) -> Surface:
    freq_x = abs(parse_number(params.get("freq_x", 0.0), 0.0))
    freq_y = abs(parse_number(params.get("freq_y", 0.0), 0.0))
    freq_x = max(freq_x, 1e-4)
    freq_y = max(freq_y, 1e-4)
    num_octaves = int(params.get("octaves", 1))
    num_octaves = max(1, min(num_octaves, 8))
    seed = int(params.get("seed", 0))
    turbulence_type = params.get("turbulence_type", "turbulence")
    stitch_tiles = str(params.get("stitch", "noStitch")).strip().lower() == "stitch"

    rng = np.random.default_rng(seed)
    if stitch_tiles:
        x = np.linspace(0.0, 1.0, num=max(width, 1), endpoint=False, dtype=np.float32)
        y = np.linspace(0.0, 1.0, num=max(height, 1), endpoint=False, dtype=np.float32)
    else:
        x = (np.arange(width, dtype=np.float32) + 0.5) / max(width, 1)
        y = (np.arange(height, dtype=np.float32) + 0.5) / max(height, 1)
    grid_x, grid_y = np.meshgrid(x, y)

    total = np.zeros((height, width), dtype=np.float32)
    amplitude = 1.0
    amplitude_total = 0.0

    base_freq_x = freq_x * max(units.bbox_width, 1.0)
    base_freq_y = freq_y * max(units.bbox_height, 1.0)

    for octave in range(num_octaves):
        phase = rng.uniform(0.0, 2.0 * math.pi, size=4)
        freq_mul = 2**octave
        fx = base_freq_x * freq_mul
        fy = base_freq_y * freq_mul
        if stitch_tiles:
            if width > 0:
                fx = round(fx * width) / max(width, 1)
            if height > 0:
                fy = round(fy * height) / max(height, 1)
        sample = (
            np.sin(2.0 * math.pi * fx * grid_x + phase[0])
            + np.sin(2.0 * math.pi * fy * grid_y + phase[1])
            + np.sin(2.0 * math.pi * fx * grid_y + phase[2])
            + np.sin(2.0 * math.pi * fy * grid_x + phase[3])
        )
        if turbulence_type == "turbulence":
            sample = np.abs(sample)
        total += sample * amplitude
        amplitude_total += amplitude
        amplitude *= 0.5

    total -= total.min()
    total /= total.max() + _lighting._EPSILON
    if stitch_tiles:
        total[:, -1] = total[:, 0]
        total[-1, :] = total[0, :]

    surface = Surface.make(width, height)
    _ = linear  # linear turbulence output is already generated in the active work space.
    surface.data[..., :3] = total[..., None]
    surface.data[..., 3] = 1.0
    return surface


def place_image_surface(image: Surface, width: int, height: int) -> Surface:
    result = Surface.make(width, height)
    w = min(width, image.width)
    h = min(height, image.height)
    result.data[:h, :w, :] = image.data[:h, :w, :]
    return result


def apply_flood(width: int, height: int, attrs: Mapping[str, str], styles: Mapping[str, str], mode: str) -> Surface:
    color_value = attrs.get("flood-color") or styles.get("flood-color") or "#000000"
    opacity_value = attrs.get("flood-opacity") or styles.get("flood-opacity")
    opacity = parse_opacity(opacity_value, 1.0)
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


def apply_composite(
    a: Surface,
    b: Surface,
    operator: str,
    *,
    k1: float = 0.0,
    k2: float = 0.0,
    k3: float = 0.0,
    k4: float = 0.0,
) -> Surface:
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
    elif operator == "arithmetic":
        out_rgb = k1 * src_rgb * dst_rgb + k2 * src_rgb + k3 * dst_rgb + k4
        out_alpha = k1 * src_alpha * dst_alpha + k2 * src_alpha + k3 * dst_alpha + k4
        out_rgb = np.clip(out_rgb, 0.0, 1.0)
        out_alpha = np.clip(out_alpha, 0.0, 1.0)
    else:
        out_rgb = src_rgb
        out_alpha = src_alpha

    result.data[..., :3] = out_rgb
    result.data[..., 3:4] = out_alpha
    return result


def apply_blend(a: Surface, b: Surface, mode: str | None, linear: bool) -> Surface:
    mode = (mode or "normal").strip().lower()
    _ = linear  # linear interpolation placeholder for future enhancements
    src = a.data.copy()
    dst = b.data.copy()

    src_rgb = src[..., :3]
    dst_rgb = dst[..., :3]
    src_alpha = np.clip(src[..., 3:4], 0.0, 1.0)
    dst_alpha = np.clip(dst[..., 3:4], 0.0, 1.0)

    with np.errstate(divide="ignore", invalid="ignore"):
        src_un = np.where(src_alpha > 0, src_rgb / src_alpha, 0.0)
        dst_un = np.where(dst_alpha > 0, dst_rgb / dst_alpha, 0.0)

    if mode == "multiply":
        blend_un = src_un * dst_un
    elif mode == "screen":
        blend_un = src_un + dst_un - src_un * dst_un
    elif mode == "darken":
        blend_un = np.minimum(src_un, dst_un)
    elif mode == "lighten":
        blend_un = np.maximum(src_un, dst_un)
    else:
        blend_un = src_un

    blend_un = np.clip(blend_un, 0.0, 1.0)
    blend_rgb = blend_un * (src_alpha * dst_alpha)

    out_alpha = src_alpha + dst_alpha - src_alpha * dst_alpha
    out_rgb = blend_rgb + (1.0 - src_alpha) * dst_rgb + (1.0 - dst_alpha) * src_rgb
    out_rgb = np.clip(out_rgb, 0.0, 1.0)

    result = Surface.make(a.width, a.height)
    result.data[..., :3] = out_rgb
    result.data[..., 3:4] = np.clip(out_alpha, 0.0, 1.0)
    return result


def _gaussian_kernel(sigma: float) -> np.ndarray:
    sigma = max(float(sigma), _lighting._EPSILON)
    radius = max(int(3 * sigma + 0.5), 1)
    x = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-(x**2) / (2.0 * sigma * sigma))
    kernel /= kernel.sum()
    return kernel.astype(np.float32)


def _apply_transfer_function(values: np.ndarray, func: ComponentTransferFunction) -> np.ndarray:
    if func.func_type == "identity" or func.func_type is None:
        return values.copy()
    if func.func_type == "linear":
        return np.clip(func.slope * values + func.intercept, 0.0, 1.0).astype(np.float32)
    if func.func_type == "table" and func.values is not None:
        table = np.clip(func.values, 0.0, 1.0).astype(np.float32)
        if table.size == 0:
            return values.copy()
        xp = np.linspace(0.0, 1.0, num=table.size, dtype=np.float32)
        flat = np.interp(np.clip(values, 0.0, 1.0).ravel(), xp, table)
        return flat.reshape(values.shape).astype(np.float32)
    return values.copy()


def _morph_channel(channel: np.ndarray, rx: int, ry: int, dilate: bool) -> np.ndarray:
    if rx == 0 and ry == 0:
        return channel.copy()
    padded = np.pad(channel, ((ry, ry), (rx, rx)), mode="edge")
    height, width = channel.shape
    result = np.empty_like(channel)
    for y in range(height):
        y0 = y
        y1 = y + 2 * ry + 1
        window = padded[y0:y1, :]
        for x in range(width):
            x0 = x
            x1 = x + 2 * rx + 1
            patch = window[:, x0:x1]
            result[y, x] = np.max(patch) if dilate else np.min(patch)
    return result


def _resolve_input_surface(images: Mapping[str, Surface], name: str | None, fallback: Surface) -> Surface:
    if not name:
        return fallback.clone()
    surface = images.get(name)
    if surface is None:
        return fallback.clone()
    return surface.clone()


__all__ = [
    "apply_blend",
    "apply_color_matrix",
    "apply_component_transfer",
    "apply_composite",
    "apply_flood",
    "apply_gaussian_blur",
    "apply_merge",
    "apply_morphology",
    "apply_offset",
    "apply_turbulence",
    "extract_alpha",
    "place_image_surface",
    "resolve_inputs",
]
