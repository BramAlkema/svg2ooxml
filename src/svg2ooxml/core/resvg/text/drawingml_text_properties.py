"""DrawingML text property conversion helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from svg2ooxml.color.adapters import color_object_to_hex

if TYPE_CHECKING:
    from svg2ooxml.core.resvg.painting.paint import Color as ResvgColor


DRAWINGML_HUNDREDTHS_PER_POINT = 100


def _parse_font_weight(font_weight: str | None) -> int:
    """Parse SVG font-weight to numeric value in the 100-900 range."""
    if not font_weight:
        return 400

    weight_lower = font_weight.lower().strip()
    if weight_lower == "normal":
        return 400
    if weight_lower == "bold":
        return 700
    if weight_lower == "bolder":
        return 700
    if weight_lower == "lighter":
        return 300

    try:
        weight_num = int(weight_lower)
        return max(100, min(900, weight_num))
    except ValueError:
        return 400


def _map_font_weight(font_weight: str | None) -> bool:
    """Convert SVG font-weight to a DrawingML bold flag."""
    return _parse_font_weight(font_weight) >= 700


def _map_font_style(font_style: str | None) -> bool:
    """Convert SVG font-style to a DrawingML italic flag."""
    if not font_style:
        return False
    return font_style.lower().strip() in ("italic", "oblique")


def _color_to_hex(color: ResvgColor | None) -> str:
    """Convert resvg Color to a 6-character uppercase sRGB hex string."""
    return color_object_to_hex(color, scale="unit") or "000000"


def _font_size_pt_to_drawingml(size_pt: float) -> int:
    """Convert font size from points to DrawingML hundredths of a point."""
    if size_pt <= 0:
        raise ValueError(f"Font size must be positive, got {size_pt}")
    hundredths = round(size_pt * DRAWINGML_HUNDREDTHS_PER_POINT)
    return max(1, hundredths)


__all__ = [
    "DRAWINGML_HUNDREDTHS_PER_POINT",
    "_color_to_hex",
    "_font_size_pt_to_drawingml",
    "_map_font_style",
    "_map_font_weight",
    "_parse_font_weight",
]
