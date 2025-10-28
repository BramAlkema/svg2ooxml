"""Compatibility wrapper for resvg clip/mask helpers."""

from svg2ooxml.core.traversal.bridges import (
    collect_resvg_clip_definitions,
    collect_resvg_mask_info,
)

__all__ = ["collect_resvg_clip_definitions", "collect_resvg_mask_info"]
