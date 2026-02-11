"""Register the filter service provider."""

from __future__ import annotations

try:  # pragma: no cover - optional dependency
    import numpy as _np  # noqa: F401
    _NUMPY_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency missing
    _NUMPY_AVAILABLE = False

from .registry import register_provider


def _factory():
    if _NUMPY_AVAILABLE:
        from svg2ooxml.services.filter_service import FilterService

        return FilterService()
    from svg2ooxml.services.filter_service_stub import DisabledFilterService

    return DisabledFilterService(reason="numpy_missing")


register_provider("filter", _factory)


__all__ = ["_factory"]
