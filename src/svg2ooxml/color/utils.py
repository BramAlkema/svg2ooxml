"""Utility helpers for colour conversions."""

from __future__ import annotations

from typing import Literal

from .parsers import parse_color

__all__ = ["color_to_hex", "rgb_channels_to_hex", "rgb_object_to_hex"]


def color_to_hex(value: str | None, *, default: str = "000000") -> str:
    """Convert CSS-style colour strings to an uppercase 6-digit hex."""

    if not value:
        return default.upper()

    try:
        colour = parse_color(value)
        if colour is None:
            raise ValueError("unparseable")
        hex_value = colour.to_hex(include_alpha=False)
        return hex_value[1:].upper()
    except Exception:
        return default.upper()


def rgb_object_to_hex(
    color: object | None,
    *,
    default: str | None = "000000",
    prefix: str = "",
    scale: Literal["unit", "byte", "auto"] = "unit",
) -> str | None:
    """Convert an object with ``r``, ``g``, ``b`` attributes to uppercase hex."""

    if color is None:
        return default
    try:
        return rgb_channels_to_hex(
            float(color.r),
            float(color.g),
            float(color.b),
            prefix=prefix,
            scale=scale,
        )
    except (TypeError, ValueError, AttributeError):
        return default


def rgb_channels_to_hex(
    r: float,
    g: float,
    b: float,
    *,
    prefix: str = "",
    scale: Literal["unit", "byte", "auto"] = "byte",
) -> str:
    """Convert numeric RGB channels to uppercase hex."""

    red = _coerce_channel(float(r), scale=scale)
    green = _coerce_channel(float(g), scale=scale)
    blue = _coerce_channel(float(b), scale=scale)
    return f"{prefix}{red:02X}{green:02X}{blue:02X}"


def _coerce_channel(value: float, *, scale: Literal["unit", "byte", "auto"]) -> int:
    if scale == "byte":
        return int(max(0.0, min(255.0, value)))
    if scale == "auto" and value > 1.0:
        return int(round(max(0.0, min(255.0, value))))
    return int(round(max(0.0, min(1.0, value)) * 255))
