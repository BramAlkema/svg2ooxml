"""Register the filter service provider."""

from __future__ import annotations

from svg2ooxml.services.filter_service import FilterService

from .registry import register_provider


def _factory() -> FilterService:
    return FilterService()


register_provider("filter", _factory)


__all__ = ["_factory"]
