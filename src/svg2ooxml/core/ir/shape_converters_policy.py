"""Policy and tracing helpers for SVG shape conversion."""

from __future__ import annotations

from typing import Any

from lxml import etree

from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.ir.paint import (
    LinearGradientPaint,
    PatternPaint,
    RadialGradientPaint,
    SolidPaint,
)
from svg2ooxml.policy.constants import FALLBACK_BITMAP, FALLBACK_EMF

_NATIVE_FILL_TYPES = (SolidPaint, LinearGradientPaint, RadialGradientPaint)


class ShapeConversionPolicyMixin:
    def _trace_geometry_decision(
        self,
        element: etree._Element,
        decision: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        tracer = getattr(self, "_tracer", None)
        if tracer is None:
            return
        tag = local_name(element.tag) if isinstance(element.tag, str) else ""
        element_id = element.get("id") if hasattr(element, "get") else None
        tracer.record_geometry_decision(
            tag=tag,
            decision=decision,
            metadata=dict(metadata) if isinstance(metadata, dict) else metadata,
            element_id=element_id,
        )

    @staticmethod
    def _fill_can_render_natively(fill, metadata: dict[str, Any]) -> bool:
        if isinstance(fill, _NATIVE_FILL_TYPES):
            return True
        if not isinstance(fill, PatternPaint):
            return False

        policy = metadata.get("policy", {}) if isinstance(metadata, dict) else {}
        geometry_policy = policy.get("geometry", {}) if isinstance(policy, dict) else {}
        paint_policy = policy.get("paint", {}) if isinstance(policy, dict) else {}
        fill_policy = paint_policy.get("fill", {}) if isinstance(paint_policy, dict) else {}

        for entry in (fill_policy, geometry_policy):
            if isinstance(entry, dict) and entry.get("suggest_fallback") in {
                FALLBACK_EMF,
                FALLBACK_BITMAP,
            }:
                return False
        return True

    @staticmethod
    def _pattern_fill_requires_path_fallback(fill) -> bool:
        if not isinstance(fill, PatternPaint):
            return False
        if fill.tile_image or fill.tile_relationship_id:
            return False

        transform = fill.transform
        if transform is None:
            return False

        matrix = transform.tolist() if hasattr(transform, "tolist") else transform
        identity = (
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        )
        try:
            for row_idx, row in enumerate(matrix):
                for col_idx, value in enumerate(row):
                    if abs(float(value) - identity[row_idx][col_idx]) >= 1e-9:
                        return True
            return False
        except (TypeError, ValueError, IndexError):
            return True

    @staticmethod
    def _prefer_pattern_path_fallback(
        metadata: dict[str, Any],
        *,
        allow_emf_fallback: bool,
        allow_bitmap_fallback: bool,
    ) -> str | None:
        geometry_policy = metadata.setdefault("policy", {}).setdefault("geometry", {})
        if allow_bitmap_fallback:
            geometry_policy.setdefault("suggest_fallback", FALLBACK_BITMAP)
            return FALLBACK_BITMAP
        return None

    @staticmethod
    def _prefer_non_native_fill_fallback(
        fill,
        *,
        allow_emf_fallback: bool,
        allow_bitmap_fallback: bool,
    ) -> str | None:
        if isinstance(fill, PatternPaint):
            if allow_bitmap_fallback:
                return FALLBACK_BITMAP
            return None
        if allow_bitmap_fallback:
            return FALLBACK_BITMAP
        if allow_emf_fallback:
            return FALLBACK_EMF
        return None


__all__ = ["ShapeConversionPolicyMixin"]
