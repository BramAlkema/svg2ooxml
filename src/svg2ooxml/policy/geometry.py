"""Geometry policy helpers for path simplification and fallbacks.

This module centralises the policy-driven adjustments that used to live inside
the mapping layer so callers can reuse the same logic across the pipeline.
See ADR-geometry-ir for the broader migration plan.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from svg2ooxml.ir.geometry import SegmentType
from svg2ooxml.policy.constants import FALLBACK_BITMAP, FALLBACK_EMF, FALLBACK_NATIVE


def apply_geometry_policy(
    segments: Sequence[SegmentType],
    policy: Mapping[str, Any] | None,
) -> tuple[list[SegmentType], dict[str, Any], str]:
    """Apply geometry policy decisions to path segments.

    Returns a tuple ``(segments, metadata, mode)`` where:

    * ``segments`` – the (possibly simplified) segment list
    * ``metadata`` – policy notes describing the adjustments performed
    * ``mode`` – rendering hint (``native``/``emf``/``bitmap``)
    """
    current = list(segments)
    if not policy:
        return current, {}, FALLBACK_NATIVE

    metadata: dict[str, Any] = {}
    mode = FALLBACK_NATIVE

    force_bitmap = bool(policy.get("force_bitmap"))
    force_emf = bool(policy.get("force_emf"))
    allow_emf = bool(policy.get("allow_emf_fallback", True))
    allow_bitmap = bool(policy.get("allow_bitmap_fallback", True))

    if force_bitmap:
        mode = FALLBACK_BITMAP
    elif force_emf:
        mode = FALLBACK_EMF

    max_segments = policy.get("max_segments")
    simplify = bool(policy.get("simplify_paths"))

    if max_segments and len(current) > max_segments:
        metadata["segment_count_before"] = len(current)
        if simplify:
            step = max(1, math.ceil(len(current) / max_segments))
            simplified = current[::step]
            if simplified and simplified[-1] is not current[-1]:
                simplified.append(current[-1])
            current = simplified
            metadata["segment_count_after"] = len(current)
            metadata["simplified"] = True
            if len(current) > max_segments and mode != FALLBACK_BITMAP:
                mode = FALLBACK_EMF
        elif mode != FALLBACK_BITMAP:
            mode = FALLBACK_EMF

    max_complexity = policy.get("max_complexity")
    if max_complexity is not None:
        if max_segments:
            complexity_ratio = len(current) / max_segments
        else:
            complexity_ratio = float(len(current))
        metadata["complexity_ratio"] = complexity_ratio
        if complexity_ratio > max_complexity:
            metadata.setdefault("flags", []).append("complexity_exceeded")
            if mode == FALLBACK_NATIVE:
                mode = FALLBACK_EMF

    if mode == FALLBACK_EMF and not allow_emf and not force_emf:
        mode = FALLBACK_NATIVE
    if mode == FALLBACK_BITMAP and not allow_bitmap and not force_bitmap:
        mode = FALLBACK_NATIVE

    metadata["render_mode"] = mode
    return current, metadata, mode


__all__ = ["apply_geometry_policy"]
