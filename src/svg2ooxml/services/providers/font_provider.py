"""Default font service providers."""

from __future__ import annotations

from svg2ooxml.services.fonts import (
    FontEmbeddingEngine,
    FontService,
    collect_font_directories,
)
from svg2ooxml.services.fonts.providers import DirectoryFontProvider

from .registry import register_provider


def _build_font_service() -> FontService:
    service = FontService()
    directories = collect_font_directories()
    if directories:
        service.register_provider(DirectoryFontProvider(directories))
    return service


def _build_embedding_engine() -> FontEmbeddingEngine:
    return FontEmbeddingEngine()


register_provider("font", _build_font_service)
register_provider("font_embedding", _build_embedding_engine)


__all__ = ["_build_font_service", "_build_embedding_engine"]
