"""Optional skia backend binding for DrawingML rasterization."""

from __future__ import annotations

try:  # pragma: no cover - optional dependency
    import skia

    SKIA_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    skia = None  # type: ignore
    SKIA_AVAILABLE = False


__all__ = ["SKIA_AVAILABLE", "skia"]
