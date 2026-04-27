"""Color conversion utilities."""

from __future__ import annotations

from svg2ooxml.color.adapters import hex_to_rgb_tuple
from svg2ooxml.color.parsers import parse_color as _parse_color
from svg2ooxml.color.utils import color_to_hex, rgb_channels_to_hex

__all__ = [
    "color_to_hex",
    "parse_color",
    "hex_to_rgb",
    "rgb_to_hex",
]


def parse_color(value: str | None):
    """
    Parse color string to Color object.

    Args:
        value: Color string (hex, rgb, named color, etc.)

    Returns:
        Color object or None if parsing fails

    Example:
        >>> color = parse_color("#FF0000")
        >>> color = parse_color("rgb(255, 0, 0)")
        >>> color = parse_color("red")
    """
    return _parse_color(value)


def hex_to_rgb(hex_value: str) -> tuple[int, int, int]:
    """
    Convert hex color to RGB tuple.

    Args:
        hex_value: Hex color like "FF0000" or "#FF0000"

    Returns:
        (r, g, b) tuple with values 0-255

    Raises:
        ValueError: If hex_value is not a valid 6-digit hex color

    Example:
        >>> hex_to_rgb("FF0000")
        (255, 0, 0)
        >>> hex_to_rgb("#00FF00")
        (0, 255, 0)
    """
    hex_clean = hex_value.lstrip("#")
    if len(hex_clean) != 6:
        raise ValueError(f"Invalid hex color: {hex_value!r}, expected 6 hex digits")

    try:
        return hex_to_rgb_tuple(hex_clean)
    except ValueError as e:
        raise ValueError(f"Invalid hex color: {hex_value!r}") from e


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """
    Convert RGB to hex color (without #).

    Args:
        r: Red component 0-255
        g: Green component 0-255
        b: Blue component 0-255

    Returns:
        Hex string like "FF0000" (uppercase, no #)

    Example:
        >>> rgb_to_hex(255, 0, 0)
        'FF0000'
        >>> rgb_to_hex(0, 255, 0)
        '00FF00'
    """
    return rgb_channels_to_hex(r, g, b, scale="byte")
