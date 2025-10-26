"""Shared policy-related constants."""

from __future__ import annotations

from typing import Final

# Fallback hints used across geometry and paint metadata.
FALLBACK_NATIVE: Final[str] = "native"
FALLBACK_EMF: Final[str] = "emf"
FALLBACK_BITMAP: Final[str] = "bitmap"
FALLBACK_RASTERIZE: Final[str] = "rasterize"


def geometry_fallback_for(paint_fallback: str | None) -> str | None:
    """Normalize paint fallback hints for geometry metadata consistency."""

    if paint_fallback is None:
        return None
    fallback = paint_fallback.lower()
    if fallback == FALLBACK_RASTERIZE:
        return FALLBACK_EMF
    if fallback in {FALLBACK_NATIVE, FALLBACK_EMF, FALLBACK_BITMAP}:
        return fallback
    return fallback


__all__ = [
    "FALLBACK_BITMAP",
    "FALLBACK_EMF",
    "FALLBACK_NATIVE",
    "FALLBACK_RASTERIZE",
    "geometry_fallback_for",
]
