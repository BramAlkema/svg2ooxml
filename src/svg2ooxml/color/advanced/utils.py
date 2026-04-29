#!/usr/bin/env python3
"""
Utility helpers for working with the Clean Slate color system.
"""

from __future__ import annotations

from svg2ooxml.color.utils import color_to_hex as _color_to_hex


def color_to_hex(value: str | None, default: str = "000000") -> str:
    """
    Convert any CSS-style color value (named colors, hex, rgb()) to a 6-digit hex string.

    Args:
        value: Color string; when None or invalid the default is returned.
        default: Hex string (without '#') returned when parsing fails.

    Returns:
        Uppercase 6-digit hex string without leading '#'.
    """
    return _color_to_hex(value, default=default)
