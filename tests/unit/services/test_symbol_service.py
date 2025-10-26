"""Tests for the symbol service helper."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.services.conversion import ConversionServices
from svg2ooxml.services.symbol_service import SymbolService


def _build_symbol(markup: str) -> etree._Element:
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg'>"
        f"{markup}"
        "</svg>"
    )
    root = etree.fromstring(svg)
    return root[0]


def test_symbol_service_stores_definitions() -> None:
    symbol_element = _build_symbol("<symbol id='icon'><rect width='10' height='10'/></symbol>")

    service = SymbolService()
    service.update_definitions({"icon": symbol_element})

    assert service.get("icon") is symbol_element
    assert service.require("icon") is symbol_element
    assert list(service.ids()) == ["icon"]


def test_symbol_service_clone_copies_definitions() -> None:
    symbol_element = _build_symbol("<symbol id='icon'><rect width='5' height='5'/></symbol>")
    service = SymbolService()
    service.register("icon", symbol_element)

    clone = service.clone()

    assert clone.get("icon") is symbol_element
    clone.register("other", _build_symbol("<symbol id='other'><circle r='2'/></symbol>"))
    assert "other" in clone.ids()
    assert "other" not in service.ids()


def test_symbol_service_binds_from_conversion_services() -> None:
    services = ConversionServices()
    symbol_element = _build_symbol("<symbol id='icon'><rect width='10' height='10'/></symbol>")

    services.register("symbols", {"icon": symbol_element})

    symbol_service = SymbolService()
    symbol_service.bind_services(services)

    assert symbol_service.require("icon") is symbol_element
