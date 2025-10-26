"""Register the symbol service provider."""

from __future__ import annotations

from svg2ooxml.services.symbol_service import SymbolService

from .registry import register_provider


def _factory() -> SymbolService:
    return SymbolService()


register_provider("symbol", _factory)


__all__ = ["_factory"]
