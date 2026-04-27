"""Shared paint utilities for gradient and pattern resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from svg2ooxml.policy.constants import FALLBACK_EMF as FALLBACK_EMF
from svg2ooxml.policy.constants import geometry_fallback_for

if TYPE_CHECKING:  # pragma: no cover - hint only
    from svg2ooxml.core.tracing import ConversionTracer


def ensure_paint_policy(
    metadata: dict[str, Any], role: str
) -> dict[str, Any]:
    policy = metadata.setdefault("policy", {})
    paint_policy = policy.setdefault("paint", {})
    entry = paint_policy.setdefault(role, {})
    return entry


def maybe_set_geometry_fallback(
    metadata: dict[str, Any],
    fallback: str,
    tracer: ConversionTracer | None,
) -> None:
    normalized = geometry_fallback_for(fallback)
    if normalized is None:
        return
    geometry_policy = metadata.setdefault("policy", {}).setdefault("geometry", {})
    if geometry_policy.get("suggest_fallback") is None:
        geometry_policy["suggest_fallback"] = normalized
        if tracer is not None:
            tracer.record_stage_event(
                stage="geometry",
                action="fallback_requested",
                metadata={"fallback": normalized},
            )
