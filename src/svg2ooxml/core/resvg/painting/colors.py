"""Basic color utilities until full paint models are ported."""

from __future__ import annotations

from svg2ooxml.color.adapters import hex_to_rgb_tuple


def parse_rgb(hex_value: str) -> tuple[int, int, int]:
    """Parse a short-form hex color (#RRGGBB)."""
    if not hex_value.startswith("#") or len(hex_value) != 7:
        raise ValueError(f"Unsupported color format: {hex_value!r}")
    return hex_to_rgb_tuple(hex_value)
