"""Tests for the color matrix filter integration."""

from __future__ import annotations

from lxml import etree
from tests.unit.filters.policy import assert_fallback, assert_strategy

from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.services.filter_service import FilterService
from svg2ooxml.services.filter_types import FilterEffectResult


def _make_service() -> FilterService:
    service = FilterService()
    service.bind_services = getattr(service, "bind_services", lambda services: None)
    return service


def test_color_matrix_saturate_uses_raster_fallback() -> None:
    """feColorMatrix(saturate) has no valid effectLst equivalent — uses raster fallback."""
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='cm'><feColorMatrix type='saturate' values='0.5'/></filter>"
    )
    service.register_filter("cm", filter_xml)

    results = service.resolve_effects("cm")

    assert results
    first = results[0]
    assert isinstance(first, FilterEffectResult)
    assert_fallback(first, modern="bitmap")
    assert_strategy(first, modern="raster")
    assert isinstance(first.effect, CustomEffect)
    assert first.effect.drawingml.startswith("<a:effectLst>")


def test_color_matrix_matrix_flags_fallback() -> None:
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='cm'><feColorMatrix type='matrix' values='" + " ".join(["1"] * 20) + "'/></filter>"
    )
    service.register_filter("cm", filter_xml)

    results = service.resolve_effects("cm")

    assert results
    first = results[0]
    assert_fallback(first, modern="emf")
    assert_strategy(first, modern="vector")
    assert first.effect.drawingml.startswith("<a:effectLst>")
    assets = first.metadata.get("fallback_assets")
    assert assets and assets[0]["type"] == "emf"
    assert assets[0].get("metadata", {}).get("filter_type") == "color_matrix"


def test_color_matrix_saturate_enriches_blip_when_policy_enabled() -> None:
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='cm'><feColorMatrix type='saturate' values='0.5'/></filter>"
    )
    service.register_filter("cm", filter_xml)

    results = service.resolve_effects(
        "cm",
        context={
            "policy": {
                "enable_native_color_transforms": True,
                "enable_blip_effect_enrichment": True,
            }
        },
    )

    assert results
    first = results[0]
    assert "<a:satMod val=\"50000\"/>" in first.effect.drawingml
    assert first.metadata.get("blip_effect_enrichment_applied") is True
