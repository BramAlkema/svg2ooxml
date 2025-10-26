"""Register the pattern service provider."""

from __future__ import annotations

from svg2ooxml.services.pattern_service import PatternService

from .registry import register_provider


def _factory() -> PatternService:
    return PatternService()


register_provider("pattern", _factory)


__all__ = ["_factory"]
