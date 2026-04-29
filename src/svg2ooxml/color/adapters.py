"""Boundary adapters for color parser results and foreign color objects."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from svg2ooxml.color.models import Color
from svg2ooxml.color.parsers import parse_color
from svg2ooxml.color.utils import rgb_channels_to_hex, rgb_object_to_hex
from svg2ooxml.common.math_utils import clamp01

RgbaTuple = tuple[float, float, float, float]
RgbScale = Literal["unit", "byte", "auto"]


def css_color_to_hex(
    value: object | None,
    *,
    default: str = "000000",
    prefix: str = "",
    current_color: Color | RgbaTuple | None = None,
    palette: Mapping[str, Color | str] | None = None,
) -> str:
    """Resolve a CSS/SVG color token to uppercase RGB hex."""

    if value is None:
        return _format_default(default, prefix=prefix)
    color = parse_color(
        value,
        current_color=_coerce_current_color(current_color),
        palette=palette,
    )
    if color is None:
        return _format_default(default, prefix=prefix)
    return rgb_channels_to_hex(color.r, color.g, color.b, prefix=prefix, scale="unit")


def color_to_rgba_tuple(
    value: object | None,
    *,
    current_color: Color | RgbaTuple | None = None,
    palette: Mapping[str, Color | str] | None = None,
    default: RgbaTuple | None = None,
) -> RgbaTuple | None:
    """Resolve a CSS/SVG color token to a normalized RGBA tuple."""

    color = parse_color(
        value,
        current_color=_coerce_current_color(current_color),
        palette=palette,
    )
    if color is None:
        return default
    clamped = color.clamp()
    return (clamped.r, clamped.g, clamped.b, clamped.a)


def hex_to_rgba_tuple(
    value: str | None,
    *,
    default: RgbaTuple | None = None,
) -> RgbaTuple | None:
    """Parse a hex color into a normalized RGBA tuple."""

    return color_to_rgba_tuple(value, default=default)


def rgba_tuple_to_hex(value: RgbaTuple, *, prefix: str = "") -> str:
    """Convert a normalized RGBA tuple to uppercase RGB hex."""

    r, g, b, _a = value
    return rgb_channels_to_hex(r, g, b, prefix=prefix, scale="unit")


def hex_to_rgb_tuple(value: str) -> tuple[int, int, int]:
    """Parse a hex color into byte RGB channels."""

    rgba = hex_to_rgba_tuple(value)
    if rgba is None:
        raise ValueError(f"Invalid hex color: {value!r}")
    r, g, b, _a = rgba
    return (
        _unit_to_byte(r),
        _unit_to_byte(g),
        _unit_to_byte(b),
    )


def color_object_to_hex(
    color: object | None,
    *,
    default: str | None = "000000",
    prefix: str = "",
    scale: RgbScale = "auto",
) -> str | None:
    """Convert any object exposing ``r``, ``g``, ``b`` to uppercase RGB hex."""

    formatted_default = (
        _format_default(default, prefix=prefix) if default is not None else None
    )
    return rgb_object_to_hex(
        color,
        default=formatted_default,
        prefix=prefix,
        scale=scale,
    )


def color_object_alpha(color: object | None, *, default: float = 1.0) -> float:
    """Return a clamped alpha value from a foreign color object."""

    if color is None:
        return _clamp01(default)
    try:
        alpha = float(getattr(color, "a", default))
    except (TypeError, ValueError):
        return _clamp01(default)
    if alpha > 1.0:
        alpha /= 255.0
    return _clamp01(alpha)


def _coerce_current_color(value: Color | RgbaTuple | None) -> Color | None:
    if value is None:
        return None
    if isinstance(value, Color):
        return value
    if len(value) == 3:
        return Color(value[0], value[1], value[2], 1.0).clamp()
    return Color(value[0], value[1], value[2], value[3]).clamp()


def _format_default(default: str | None, *, prefix: str) -> str:
    token = "" if default is None else str(default).strip()
    if not token:
        token = "000000"
    token = token.lstrip("#").upper()
    return f"{prefix}{token}" if prefix else token


def _unit_to_byte(value: float) -> int:
    return int(round(_clamp01(value) * 255.0))


def _clamp01(value: float) -> float:
    return clamp01(value)


__all__ = [
    "RgbaTuple",
    "RgbScale",
    "color_object_alpha",
    "color_object_to_hex",
    "color_to_rgba_tuple",
    "css_color_to_hex",
    "hex_to_rgb_tuple",
    "hex_to_rgba_tuple",
    "rgba_tuple_to_hex",
]
