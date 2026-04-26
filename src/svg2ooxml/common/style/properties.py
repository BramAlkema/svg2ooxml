"""CSS property value conversion helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from svg2ooxml.color.utils import rgb_channels_to_hex
from svg2ooxml.common.conversions.opacity import parse_opacity
from svg2ooxml.core.parser.colors import parse_color

if TYPE_CHECKING:
    from svg2ooxml.common.style.model import StyleContext
    from svg2ooxml.core.parser.units import UnitConverter


def strip_quotes(value: str) -> str:
    return value.strip("\"'")


def normalize_font_weight(value: str) -> str:
    token = value.strip().lower()
    mapping = {
        "100": "lighter",
        "200": "lighter",
        "300": "light",
        "400": "normal",
        "500": "normal",
        "600": "semibold",
        "700": "bold",
        "800": "bolder",
        "900": "bolder",
    }
    return mapping.get(token, token)


def normalize_text_anchor(value: str) -> str:
    return value.strip().lower()


def parse_font_size_token(
    value: str,
    base_pt: float,
    *,
    unitless_scale: float,
) -> float:
    token = value.strip().lower()
    try:
        if token.endswith("px"):
            return float(token[:-2]) * 0.75
        if token.endswith("pt"):
            return float(token[:-2])
        if token.endswith("em"):
            return float(token[:-2]) * base_pt
        if token.endswith("%"):
            return base_pt * float(token[:-1]) / 100.0
        return float(token) * unitless_scale
    except ValueError:
        return base_pt


def hex_to_rgba(color: str) -> tuple[float, float, float, float]:
    token = color.lstrip("#")
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    if len(token) != 6:
        return (0.0, 0.0, 0.0, 1.0)
    r = int(token[0:2], 16) / 255.0
    g = int(token[2:4], 16) / 255.0
    b = int(token[4:6], 16) / 255.0
    return (r, g, b, 1.0)


def rgba_to_hex(value: tuple[float, float, float, float]) -> str:
    r, g, b, _ = value
    return rgb_channels_to_hex(r, g, b, prefix="#", scale="unit")


def resolve_color_token(token: str, current_hex: str) -> str:
    stripped = token.strip()
    if not stripped:
        return current_hex
    if stripped.lower() == "none":
        return current_hex
    if stripped.startswith("url("):
        return stripped

    rgba = parse_color(stripped, current_color=hex_to_rgba(current_hex))
    if rgba is None:
        return current_hex
    return rgba_to_hex(rgba)


def length_to_px(
    unit_converter: UnitConverter,
    value: str | None,
    context: StyleContext | None,
    *,
    axis: str = "x",
) -> float:
    if value is None:
        return 0.0
    token = value.strip()
    if not token:
        return 0.0

    try:
        return float(token)
    except ValueError:
        pass

    try:
        conversion = context.conversion if context is not None else None
        return unit_converter.to_px(token, conversion, axis=axis)
    except Exception:
        return 0.0


def parse_style_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    return parse_opacity(value, default)


__all__ = [
    "hex_to_rgba",
    "length_to_px",
    "normalize_font_weight",
    "normalize_text_anchor",
    "parse_font_size_token",
    "parse_style_float",
    "resolve_color_token",
    "rgba_to_hex",
    "strip_quotes",
]
