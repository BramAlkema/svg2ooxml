"""Centralized conversion utilities for svg2ooxml.

This module provides unified conversion utilities for:
- **Units**: px ↔ EMU conversions
- **Colors**: Color parsing and hex conversions
- **Angles**: degrees/radians ↔ PowerPoint 60000ths
- **Opacity**: 0-1 scale ↔ PowerPoint 100000ths
- **Transforms**: Parse scale, translation, angle values

Usage:
    Basic conversions:
        >>> from svg2ooxml.common.conversions import degrees_to_ppt, opacity_to_ppt
        >>> rotation = degrees_to_ppt(45.0)  # 2700000
        >>> alpha = opacity_to_ppt(0.7)      # 70000

    Unified converter:
        >>> from svg2ooxml.common.conversions import PPTConverter
        >>> ppt = PPTConverter()
        >>> emu = ppt.px_to_emu(100.0)
        >>> rotation = ppt.degrees_to_ppt(45.0)
        >>> alpha = ppt.opacity_to_ppt(0.7)
        >>> color = ppt.color_to_hex("#FF0000")

PowerPoint Units:
    - **EMU** (English Metric Units): 914,400 EMU = 1 inch
    - **Angles**: 60,000 units = 1 degree
    - **Opacity**: 100,000 units = fully opaque (1.0)
"""

from __future__ import annotations

# Units
from .units import (
    UnitConverter,
    px_to_emu,
    emu_to_px,
    emu_to_unit,
    ConversionContext,
    DEFAULT_DPI,
    EMU_PER_INCH,
    EMU_PER_CM,
    EMU_PER_MM,
    EMU_PER_POINT,
    EMU_PER_PX_AT_DEFAULT_DPI,
    EMU_PER_PICA,
    EMU_PER_Q,
)

# Colors
from .colors import (
    color_to_hex,
    parse_color,
    hex_to_rgb,
    rgb_to_hex,
)

# Angles
from .angles import (
    degrees_to_ppt,
    radians_to_ppt,
    ppt_to_degrees,
    ppt_to_radians,
    PPT_ANGLE_SCALE,
)

# Opacity
from .opacity import (
    opacity_to_ppt,
    ppt_to_opacity,
    alpha_to_ppt,
    ppt_to_alpha,
    percentage_to_ppt,
    ppt_to_percentage,
    PPT_OPACITY_SCALE,
)

# Transforms
from .transforms import (
    parse_scale_pair,
    parse_translation_pair,
    parse_angle,
    parse_numeric_list,
)

# Unified converter
from .powerpoint import PPTConverter

__all__ = [
    # Units
    "UnitConverter",
    "px_to_emu",
    "emu_to_px",
    "emu_to_unit",
    "ConversionContext",
    "DEFAULT_DPI",
    "EMU_PER_INCH",
    "EMU_PER_CM",
    "EMU_PER_MM",
    "EMU_PER_POINT",
    "EMU_PER_PX_AT_DEFAULT_DPI",
    "EMU_PER_PICA",
    "EMU_PER_Q",
    # Colors
    "color_to_hex",
    "parse_color",
    "hex_to_rgb",
    "rgb_to_hex",
    # Angles
    "degrees_to_ppt",
    "radians_to_ppt",
    "ppt_to_degrees",
    "ppt_to_radians",
    "PPT_ANGLE_SCALE",
    # Opacity
    "opacity_to_ppt",
    "ppt_to_opacity",
    "alpha_to_ppt",
    "ppt_to_alpha",
    "percentage_to_ppt",
    "ppt_to_percentage",
    "PPT_OPACITY_SCALE",
    # Transforms
    "parse_scale_pair",
    "parse_translation_pair",
    "parse_angle",
    "parse_numeric_list",
    # Unified
    "PPTConverter",
]
