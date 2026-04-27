"""Geometry policy helpers for path simplification and fallbacks.

This module centralises the policy-driven adjustments that used to live inside
the mapping layer so callers can reuse the same logic across the pipeline.
See ADR-geometry-ir for the broader migration plan.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

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

    simplify_min = int(policy.get("simplify_min_segments", 16))
    if simplify and len(current) >= simplify_min:
        from svg2ooxml.common.geometry.simplify import simplify_segments

        before = len(current)
        curve_fit_tol = float(policy.get("curve_fit_tolerance_px", 1.5)) if policy.get("curve_fit_enabled", True) else 0.0
        current = simplify_segments(
            current,
            epsilon=float(policy.get("simplify_epsilon_px", 0.01)),
            bezier_flatness=float(policy.get("bezier_flatness_px", 0.5)),
            collinear_angle_deg=float(policy.get("collinear_angle_deg", 0.5)),
            rdp_tolerance=float(policy.get("rdp_tolerance_px", 1.0)),
            curve_fit_tolerance=curve_fit_tol,
            curve_fit_min_points=int(policy.get("curve_fit_min_points", 8)),
        )
        after = len(current)
        if after < before:
            metadata["segments_before_simplify"] = before
            metadata["segments_after_simplify"] = after
            metadata["simplified"] = True

    # Preset shape detection (after simplification, before fallback check)
    if bool(policy.get("detect_preset_shapes", True)) and mode == FALLBACK_NATIVE:
        from svg2ooxml.common.geometry.shape_detect import detect_preset_shape

        shape_tol = float(policy.get("shape_detect_tolerance_px", 2.0))
        match = detect_preset_shape(current, tolerance=shape_tol)
        if match is not None:
            metadata["preset_shape"] = match.preset
            metadata["preset_shape_confidence"] = match.confidence
            metadata["preset_shape_bounds"] = {
                "x": match.bounds.x, "y": match.bounds.y,
                "w": match.bounds.width, "h": match.bounds.height,
            }
            if match.corner_radius:
                metadata["preset_shape_corner_radius"] = match.corner_radius

    if max_segments and len(current) > max_segments:
        metadata["segment_count_before"] = len(current)
        if mode != FALLBACK_BITMAP:
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
