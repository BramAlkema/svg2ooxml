"""Constants and mappings for PowerPoint animation generation.

This module centralizes all constants used in animation XML generation,
including attribute categorization, name mappings, and namespace definitions.
"""

from __future__ import annotations

__all__ = [
    "FADE_ATTRIBUTES",
    "COLOR_ATTRIBUTES",
    "ANGLE_ATTRIBUTES",
    "DISPLAY_ATTRIBUTES",
    "VISIBILITY_ATTRIBUTES",
    "DISCRETE_VISIBILITY_ATTRIBUTES",
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

DISPLAY_ATTRIBUTES: frozenset[str] = frozenset({
    "display",
})
"""Attributes that gate SVG render-tree participation."""

VISIBILITY_ATTRIBUTES: frozenset[str] = frozenset({
    "visibility",
    "style.visibility",
})
"""Attributes that map to PowerPoint-native visibility state."""

DISCRETE_VISIBILITY_ATTRIBUTES: frozenset[str] = (
    DISPLAY_ATTRIBUTES | VISIBILITY_ATTRIBUTES
)
"""Discrete show/hide attributes handled by the visibility compiler."""

# ------------------------------------------------------------------ #
# Attribute Name Mappings                                            #
# ------------------------------------------------------------------ #

ATTRIBUTE_NAME_MAP: dict[str, str] = {
    # Position attributes → ppt_x/ppt_y
    "x": "ppt_x",
    "cx": "ppt_x",
    "dx": "ppt_x",
    "fx": "ppt_x",
    "left": "ppt_x",
    "right": "ppt_x",

    "y": "ppt_y",
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

    # Line width → stroke.weight
    "stroke-width": "stroke.weight",

    # Dash offset animation → Wipe entrance (line drawing effect)
    "stroke-dashoffset": "style.visibility",

    # Visibility → PowerPoint visibility property
    "visibility": "style.visibility",
}

# Attributes that should use Wipe entrance animation instead of <p:anim>
WIPE_ATTRIBUTES: frozenset[str] = frozenset({
    "stroke-dashoffset",
})

"""Map SVG attribute names to PowerPoint attribute names.

SVG uses various attribute names (x, cx, left, etc.) that all map to
PowerPoint's coordinate system. This mapping normalizes them for animation.
"""

COLOR_ATTRIBUTE_NAME_MAP: dict[str, str] = {
    "fill": "fill.color",
    "stroke": "stroke.color",
    "stop-color": "fill.color",
    "stopcolor": "fill.color",
    "flood-color": "fill.color",
    "lighting-color": "fill.color",
}
"""Map color attribute names to PowerPoint color property names.

PowerPoint slideshow playback expects property names such as
``fill.color`` and ``stroke.color`` on animation targets.
"""

AXIS_MAP: dict[str, str] = {
    "ppt_x": "x",
    "ppt_y": "y",
    "ppt_w": "width",
    "ppt_h": "height",
    "stroke.weight": "width",
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
