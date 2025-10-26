"""Symbol service helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from lxml import etree
    from .conversion import ConversionServices


@dataclass
class SymbolService:
    """Provides access to symbol definitions."""

    _symbols: dict[str, "etree._Element"] = field(default_factory=dict)
    _services: "ConversionServices | None" = None

    def bind_services(self, services: "ConversionServices") -> None:
        self._services = services
        existing = services.resolve("symbols")
        if existing:
            self.update_definitions(existing)

    def update_definitions(
        self,
        symbols: Mapping[str, "etree._Element"] | None,
    ) -> None:
        self._symbols = dict(symbols or {})

    def register(self, symbol_id: str, element: "etree._Element") -> None:
        if not symbol_id:
            raise ValueError("symbol id must be non-empty")
        self._symbols[symbol_id] = element

    def get(self, symbol_id: str) -> "etree._Element | None":
        return self._symbols.get(symbol_id)

    def require(self, symbol_id: str) -> "etree._Element":
        element = self.get(symbol_id)
        if element is None:
            raise KeyError(f"symbol {symbol_id!r} is not defined")
        return element

    def ids(self) -> Iterable[str]:
        return tuple(self._symbols.keys())

    def clone(self) -> "SymbolService":
        clone = SymbolService()
        clone._symbols = dict(self._symbols)
        return clone


__all__ = ["SymbolService"]
