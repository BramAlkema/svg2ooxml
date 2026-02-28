"""Register the filter service provider."""

from __future__ import annotations

from .registry import register_provider


def _factory():
    try:
        from svg2ooxml.services.filter_service import FilterService

        return FilterService()
    except Exception as exc:  # pragma: no cover - defensive fallback
        from svg2ooxml.services.filter_service_stub import DisabledFilterService

        return DisabledFilterService(reason=f"filter_service_unavailable:{type(exc).__name__}")


register_provider("filter", _factory)


__all__ = ["_factory"]
