"""Animation module for PowerPoint timing XML generation.

This module provides a modular, lxml-based architecture for generating
PowerPoint animation timing XML from SVG animation definitions.

Architecture:
    - xml_builders.py: lxml-based XML builders
    - value_processors.py: Value parsing & normalization (uses common.conversions)
    - tav_builder.py: Time-Animated Value list builder
    - policy.py: Policy evaluation & skip logic
    - handlers/: Animation type handlers (opacity, color, numeric, transform, motion, set)
    - constants.py: Shared constants & mappings
    - writer.py: Main public API

Usage:
    >>> from svg2ooxml.drawingml.animation import DrawingMLAnimationWriter
    >>> writer = DrawingMLAnimationWriter()
    >>> xml = writer.build(animations, timeline, tracer=tracer)

Documentation:
    See docs/architecture/animation-system.md for comprehensive architecture details.

Migration from old implementation:
    Old: from svg2ooxml.drawingml.animation_writer import DrawingMLAnimationWriter
    New: from svg2ooxml.drawingml.animation import DrawingMLAnimationWriter

    API is backward compatible. The old module is deprecated and will be removed
    in a future release.
"""

from __future__ import annotations

from .writer import DrawingMLAnimationWriter

__all__ = [
    "DrawingMLAnimationWriter",
]
