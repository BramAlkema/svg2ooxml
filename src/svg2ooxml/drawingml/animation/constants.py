"""Constants and mappings for PowerPoint animation generation.

This module centralizes all constants used in animation XML generation,
including attribute categorization, name mappings, and namespace definitions.
"""

from __future__ import annotations

__all__ = [
    "FADE_ATTRIBUTES",
    "COLOR_ATTRIBUTES",
    "ANGLE_ATTRIBUTES",
    "ATTRIBUTE_NAME_MAP",
    "COLOR_ATTRIBUTE_NAME_MAP",
    "AXIS_MAP",
    "SVG2_ANIMATION_NS",
]

# ------------------------------------------------------------------ #
# Attribute Categories                                               #
# ------------------------------------------------------------------ #

FADE_ATTRIBUTES: frozenset[str] = frozenset({
    "opacity",
    "fill-opacity",
    "stroke-opacity",
})
"""Attributes that represent opacity/transparency and trigger fade animations."""

COLOR_ATTRIBUTES: frozenset[str] = frozenset({
    "fill",
    "stroke",
    "stop-color",
    "stopcolor",
    "flood-color",
    "lighting-color",
})
"""Attributes that represent colors and trigger color animations."""

ANGLE_ATTRIBUTES: frozenset[str] = frozenset({
    "angle",
    "rotation",
    "rotate",
    "ppt_angle",
})
"""Attributes that represent angles (need conversion to PPT 60000ths)."""

# ------------------------------------------------------------------ #
# Attribute Name Mappings                                            #
# ------------------------------------------------------------------ #

ATTRIBUTE_NAME_MAP: dict[str, str] = {
    # Position attributes → ppt_x/ppt_y
    "x": "ppt_x",
    "x1": "ppt_x",
    "x2": "ppt_x",
    "cx": "ppt_x",
    "dx": "ppt_x",
    "fx": "ppt_x",
    "left": "ppt_x",
    "right": "ppt_x",

    "y": "ppt_y",
    "y1": "ppt_y",
    "y2": "ppt_y",
    "cy": "ppt_y",
    "dy": "ppt_y",
    "fy": "ppt_y",
    "top": "ppt_y",
    "bottom": "ppt_y",

    # Size attributes → ppt_w/ppt_h
    "width": "ppt_w",
    "w": "ppt_w",
    "rx": "ppt_w",

    "height": "ppt_h",
    "h": "ppt_h",
    "ry": "ppt_h",

    # Rotation attributes → ppt_angle
    "rotate": "ppt_angle",
    "rotation": "ppt_angle",
    "angle": "ppt_angle",

    # Line width → ln_w
    "stroke-width": "ln_w",
}
"""Map SVG attribute names to PowerPoint attribute names.

SVG uses various attribute names (x, cx, left, etc.) that all map to
PowerPoint's coordinate system. This mapping normalizes them for animation.
"""

COLOR_ATTRIBUTE_NAME_MAP: dict[str, str] = {
    "fill": "fillClr",
    "stroke": "lnClr",
    "stop-color": "fillClr",
    "stopcolor": "fillClr",
    "flood-color": "fillClr",
    "lighting-color": "fillClr",
}
"""Map color attribute names to PowerPoint color property names.

PowerPoint uses different names for color properties in animations
(fillClr, lnClr) than in the shape definitions.
"""

AXIS_MAP: dict[str, str] = {
    "ppt_x": "x",
    "ppt_y": "y",
    "ppt_w": "width",
    "ppt_h": "height",
    "ln_w": "width",
}
"""Map PowerPoint attribute names to axis hints for unit conversion.

Used by UnitConverter to determine which axis (x, y, width, height)
is being animated, which affects unit conversion (px → EMU).
"""

# ------------------------------------------------------------------ #
# Namespace Definitions                                              #
# ------------------------------------------------------------------ #

SVG2_ANIMATION_NS: str = "http://svg2ooxml.dev/ns/animation"
"""Custom XML namespace for svg2ooxml animation metadata.

Used to embed Bezier spline control points and other animation metadata
into PowerPoint's timing XML without conflicting with standard namespaces.
Example: <a:tav svg2:spline="0.42 0 0.58 1" .../>
"""
