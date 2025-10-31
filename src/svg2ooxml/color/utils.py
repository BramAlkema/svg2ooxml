"""Utility helpers for colour conversions."""

from __future__ import annotations

from .parsers import parse_color

__all__ = ["color_to_hex"]


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
