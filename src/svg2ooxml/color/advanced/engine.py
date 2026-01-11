"""Availability helpers for the advanced color engine."""

from __future__ import annotations

_IMPORT_ERROR: Exception | None = None

try:
    from .core import Color as AdvancedColor

    COLOR_ENGINE_AVAILABLE = True
except Exception as exc:  # pragma: no cover - defensive
    _IMPORT_ERROR = exc
    COLOR_ENGINE_AVAILABLE = False

    class AdvancedColor:  # type: ignore[no-redef]
        """Placeholder when advanced color dependencies are missing."""

        def __init__(self, *args, **kwargs) -> None:
            require_color_engine()


def require_color_engine() -> None:
    """Raise a helpful error when advanced color dependencies are missing."""

    if COLOR_ENGINE_AVAILABLE:
        return
    message = "Advanced color engine is unavailable; install svg2ooxml[color] dependencies."
    if _IMPORT_ERROR is None:
        raise RuntimeError(message)
    raise RuntimeError(message) from _IMPORT_ERROR


__all__ = ["AdvancedColor", "COLOR_ENGINE_AVAILABLE", "require_color_engine"]
