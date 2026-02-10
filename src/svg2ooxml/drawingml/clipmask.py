"""Clip and mask rendering helpers for the DrawingML writer."""

from __future__ import annotations

from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.scene import ClipRef

__all__ = [
    "clip_bounds_for",
    "clip_xml_for",
]


def clip_bounds_for(clip_ref: ClipRef | None) -> tuple[Rect | None, list[str]]:
    """Return clip bounding box and diagnostics.

    Non-standard ``<a:clipPath>`` elements are no longer emitted — this
    function extracts bounds for xfrm approximation instead.
    """
    diagnostics: list[str] = []
    if clip_ref is None:
        return None, diagnostics

    if clip_ref.custom_geometry_bounds:
        diagnostics.append(
            f"Clip {clip_ref.clip_id} bounds extracted from custom geometry."
        )
        return clip_ref.custom_geometry_bounds, diagnostics

    bbox = getattr(clip_ref, "bounding_box", None)
    if isinstance(bbox, Rect):
        diagnostics.append(
            f"Clip {clip_ref.clip_id} bounds extracted from bounding box."
        )
        return bbox, diagnostics

    diagnostics.append(
        f"Clip {clip_ref.clip_id} has no usable bounds; clip effect dropped."
    )
    return None, diagnostics


def clip_xml_for(clip_ref: ClipRef | None) -> tuple[str, list[str]]:
    """Legacy API — returns empty XML string with diagnostics.

    Non-standard ``<a:clipPath>`` elements are no longer generated.
    Kept for backward compatibility with callers that expect the old
    signature.
    """
    _bounds, diagnostics = clip_bounds_for(clip_ref)
    return "", diagnostics
