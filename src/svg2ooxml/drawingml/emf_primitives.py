"""Primitive geometry and color helpers for EMF filter fallbacks."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

from svg2ooxml.color.utils import rgb_channels_to_hex
from svg2ooxml.common.units import px_to_emu

PaletteResolver = Callable[[str, str, Mapping[str, Any]], str | None]

DEFAULT_FILTER_PALETTE: dict[str, dict[str, str]] = {
    "composite": {
        "background": "#F5F6FF",
        "primary_layer": "#4F83FF",
        "secondary_layer": "#FF7A85",
        "outline": "#203364",
        "accent": "#1B1B1B",
    },
    "blend": {
        "background": "#FDF3F8",
        "left": "#FFBF69",
        "right": "#5A8DEE",
        "overlap": "#B57FD8",
        "accent": "#3A3A3A",
    },
    "component_transfer": {
        "background": "#F4F6FB",
        "axis": "#203040",
        "graph": "#1B1B1B",
        "grid": "#314A72",
        "channel_r": "#ED6B6B",
        "channel_g": "#5BB974",
        "channel_b": "#4F83FF",
        "channel_a": "#9E9E9E",
    },
    "color_matrix": {
        "background": "#F7F9FF",
        "grid": "#2F3E6B",
        "header": "#90A3DC",
    },
    "displacement_map": {
        "background": "#EDF2FF",
        "grid": "#7C96FF",
        "warp": "#203A84",
        "accent": "#FF6B6B",
    },
    "turbulence": {
        "background": "#F2F6FF",
        "wave_0": "#6486FF",
        "wave_1": "#314A8A",
        "wave_2": "#90A4FF",
        "wave_3": "#2A3563",
    },
    "convolve_matrix": {
        "background": "#F5F7FF",
        "grid": "#314074",
        "accent": "#FF6A6A",
    },
    "tile": {
        "background": "#F1F4FF",
        "grid": "#2F3E6B",
        "tile_0": "#6585F6",
        "tile_1": "#FDBB5A",
        "tile_2": "#8BD6FF",
    },
    "diffuse_lighting": {
        "base": "#E4EBFF",
        "accent": "#FFFFFF",
    },
    "specular_lighting": {
        "base": "#1E2A3D",
        "accent": "#FFFFFF",
    },
}


def rect_points(
    left_px: float, top_px: float, width_px: float, height_px: float
) -> list[tuple[int, int]]:
    left = px(value=left_px)
    top = px(value=top_px)
    right = px(value=left_px + width_px)
    bottom = px(value=top_px + height_px)
    return [(left, top), (right, top), (right, bottom), (left, bottom)]


def rounded_rect(
    left_px: float,
    top_px: float,
    width_px: float,
    height_px: float,
    *,
    radius: float,
) -> list[tuple[int, int]]:
    r = max(0.0, min(radius, min(width_px, height_px) / 2.0))
    points = [
        (left_px + r, top_px),
        (left_px + width_px - r, top_px),
        (left_px + width_px, top_px + r),
        (left_px + width_px, top_px + height_px - r),
        (left_px + width_px - r, top_px + height_px),
        (left_px + r, top_px + height_px),
        (left_px, top_px + height_px - r),
        (left_px, top_px + r),
    ]
    return [(px(x), px(y)) for x, y in points]


def polyline(points_px: list[tuple[float, float]]) -> list[tuple[int, int]]:
    return [(px(x), px(y)) for x, y in points_px]


def px(value: float) -> int:
    return int(round(px_to_emu(value)))


def colorref(rgb: str) -> int:
    token = rgb.strip()
    if token.startswith("#"):
        token = token[1:]
    if len(token) != 6:
        raise ValueError(f"expected 6 hex digits, got {rgb!r}")
    r = int(token[0:2], 16)
    g = int(token[2:4], 16)
    b = int(token[4:6], 16)
    return (b << 16) | (g << 8) | r


def normalise_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: normalise_value(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return tuple(normalise_value(item) for item in value)
    return value


def function_curve(
    func: dict[str, Any], left: float, top: float, width: float, height: float
) -> list[tuple[float, float]]:
    func_type = (func.get("type") or "identity").lower()
    params = func.get("params") or {}

    def clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    points: list[tuple[float, float]] = []
    if func_type == "linear":
        slope = float(params.get("slope", 1.0))
        intercept = float(params.get("intercept", 0.0))
        for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
            y = clamp(slope * t + intercept)
            points.append((left + t * width, top + (1.0 - y) * height))
    elif func_type == "gamma":
        amplitude = float(params.get("amplitude", 1.0))
        exponent = float(params.get("exponent", 1.0))
        offset = float(params.get("offset", 0.0))
        for t in [i / 10 for i in range(11)]:
            y = clamp(amplitude * (t**exponent) + offset)
            points.append((left + t * width, top + (1.0 - y) * height))
    elif func_type in {"table", "discrete"}:
        values = params.get("values") or []
        if not values:
            values = [0.0, 1.0]
        for idx, value in enumerate(values):
            x = clamp(idx / max(1, len(values) - (0 if func_type == "table" else 1)))
            y = clamp(float(value))
            x_px = left + x * width
            y_px = top + (1.0 - y) * height
            points.append((x_px, y_px))
            if func_type == "discrete" and idx < len(values) - 1:
                next_x = clamp((idx + 1) / len(values))
                points.append((left + next_x * width, y_px))
    else:
        points = [
            (left, top + height),
            (left + width, top),
        ]
    return points


def ellipse_points(
    cx_px: float,
    cy_px: float,
    rx_px: float,
    ry_px: float,
    *,
    segments: int = 12,
) -> list[tuple[int, int]]:
    if segments < 4:
        segments = 4
    pts: list[tuple[int, int]] = []
    for i in range(segments):
        theta = (2 * math.pi * i) / segments
        x = cx_px + rx_px * math.cos(theta)
        y = cy_px + ry_px * math.sin(theta)
        pts.append((px(x), px(y)))
    return pts


def adjust_lightness(hex_color: str, factor: float, *, brighten: bool) -> str:
    r, g, b = hex_to_rgb(hex_color)
    if brighten:
        r = int(r + (255 - r) * factor)
        g = int(g + (255 - g) * factor)
        b = int(b + (255 - b) * factor)
    else:
        r = int(r * (1.0 - factor))
        g = int(g * (1.0 - factor))
        b = int(b * (1.0 - factor))
    return rgb_channels_to_hex(r, g, b, prefix="#", scale="byte")


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    token = value.strip()
    if token.startswith("#"):
        token = token[1:]
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    if len(token) != 6:
        token = "888888"
    r = int(token[0:2], 16)
    g = int(token[2:4], 16)
    b = int(token[4:6], 16)
    return r, g, b


def matrix_value_color(value: float) -> str:
    clamped = max(-1.0, min(1.0, value))
    if clamped >= 0:
        blue = int(190 + clamped * 65)
        return rgb_channels_to_hex(120, 150, blue, prefix="#", scale="byte")
    red = int(190 + abs(clamped) * 65)
    return rgb_channels_to_hex(red, 140, 120, prefix="#", scale="byte")


def kernel_value_color(value: float) -> str:
    clamped = max(-5.0, min(5.0, value))
    if clamped >= 0:
        channel = int(170 + clamped / 5.0 * 70)
        return rgb_channels_to_hex(130, channel, 245, prefix="#", scale="byte")
    channel = int(170 + abs(clamped) / 5.0 * 70)
    return rgb_channels_to_hex(245, channel, 130, prefix="#", scale="byte")


def safe_float(token: str) -> float:
    try:
        return float(token)
    except (TypeError, ValueError):
        return 0.0


def resolve_with_palette(
    palette_resolver: PaletteResolver | None,
    filter_type: str,
    role: str,
    metadata: Mapping[str, Any],
) -> str | None:
    if palette_resolver is None:
        return None
    try:
        override = palette_resolver(filter_type, role, metadata)
    except Exception:
        return None
    if isinstance(override, str) and override.strip():
        return override.strip()
    return None


__all__ = [
    "DEFAULT_FILTER_PALETTE",
    "PaletteResolver",
    "adjust_lightness",
    "colorref",
    "ellipse_points",
    "function_curve",
    "hex_to_rgb",
    "kernel_value_color",
    "matrix_value_color",
    "normalise_value",
    "polyline",
    "rect_points",
    "resolve_with_palette",
    "rounded_rect",
    "safe_float",
]
