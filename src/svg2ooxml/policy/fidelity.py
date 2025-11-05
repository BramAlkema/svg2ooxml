"""Fidelity policy stubs for native vs. bake decisions."""

from __future__ import annotations

from enum import Enum
from typing import Any


class FidelityDecision(Enum):
    """Enumerator describing how a feature should be rendered."""

    NATIVE = "native"
    VECTOR_BAKE = "vector_bake"
    RASTER_BAKE = "raster_bake"


def resolve_fidelity(feature: str, *, node: Any | None = None, context: dict[str, Any] | None = None) -> FidelityDecision:
    """Return the desired fidelity strategy for a feature.

    This placeholder implementation always prefers native rendering. Future
    work will analyse the feature signature (transform, complexity thresholds,
    etc.) and return vector or raster bake directives as needed.
    """

    return FidelityDecision.NATIVE


__all__ = ["FidelityDecision", "resolve_fidelity"]
