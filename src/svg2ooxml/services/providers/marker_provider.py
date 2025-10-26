"""Register the marker service provider."""

from __future__ import annotations

from svg2ooxml.services.marker_service import MarkerService

from .registry import register_provider


def _factory() -> MarkerService:
    return MarkerService()


register_provider("marker", _factory)


__all__ = ["_factory"]
