"""Compatibility wrapper for clipping helpers."""

from __future__ import annotations

from svg2ooxml.core.traversal.clipping import *  # noqa: F401,F403

__all__ = [
    "GeometryPayload",
    "extract_url_id",
    "generate_clip_geometry",
    "resolve_clip_ref",
    "resolve_mask_ref",
]
