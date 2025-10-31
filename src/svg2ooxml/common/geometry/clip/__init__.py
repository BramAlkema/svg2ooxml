"""Helpers for tessellating clip geometry into DrawingML-friendly payloads."""

from __future__ import annotations

from .tessellation import (
    ClipPathData,
    ClipPathSegment,
    EMU_PER_PX,
    commands_to_clip_segments,
    rect_to_emu,
    tessellate_segments,
)

__all__ = [
    "ClipPathData",
    "ClipPathSegment",
    "EMU_PER_PX",
    "commands_to_clip_segments",
    "rect_to_emu",
    "tessellate_segments",
]
