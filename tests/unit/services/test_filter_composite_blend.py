"""Tests for composite and blend filter primitives."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.services.filter_service import FilterService
from svg2ooxml.services.filter_types import FilterEffectResult


def test_composite_without_inputs_falls_back_to_bitmap() -> None:
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='comp'><feComposite operator='arithmetic' k1='0.5' k2='0.25' in='SourceGraphic' in2='BackgroundImage'/></filter>"
    )
    service.register_filter("comp", filter_xml)

    results = service.resolve_effects("comp")

    assert results
    first = results[0]
    assert isinstance(first, FilterEffectResult)
    assert first.fallback == "emf"
    assert isinstance(first.effect, CustomEffect)
    assert first.metadata["operator"] == "arithmetic"
    assert "k1" in first.metadata
    assets = first.metadata.get("fallback_assets")
    assert assets and assets[0]["type"] == "emf"


def test_composite_combines_previous_result() -> None:
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='comp'>"
        "  <feGaussianBlur stdDeviation='2' result='blurred'/>"
        "  <feComposite operator='over' in='SourceGraphic' in2='blurred' result='combined'/>"
        "</filter>"
    )
    service.register_filter("comp", filter_xml)

    results = service.resolve_effects("comp")

    assert len(results) >= 2
    composite = results[1]
    assert isinstance(composite, FilterEffectResult)
    assert composite.fallback == "emf"
    assert isinstance(composite.effect, CustomEffect)
    assert composite.effect.drawingml.startswith("<a:effectLst>")
    assert composite.metadata["inputs"] == ["blurred"]
    assert composite.metadata["operator"] == "over"
    assert composite.metadata.get("native_support") is False
    assets = composite.metadata.get("fallback_assets")
    assert assets and assets[0]["type"] == "emf"
    assert assets[0].get("data_hex") or assets[0].get("data")


def test_blend_without_inputs_falls_back_to_bitmap() -> None:
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='blend'><feBlend mode='multiply' in='SourceGraphic' in2='BackgroundImage'/></filter>"
    )
    service.register_filter("blend", filter_xml)

    results = service.resolve_effects("blend")

    assert results
    first = results[0]
    assert isinstance(first, FilterEffectResult)
    assert first.fallback == "emf"
    assert isinstance(first.effect, CustomEffect)
    assert first.metadata["mode"] == "multiply"
    assets = first.metadata.get("fallback_assets")
    assert assets and assets[0]["type"] == "emf"


def test_blend_combines_previous_results() -> None:
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='blend'>"
        "  <feColorMatrix type='saturate' values='0.5' result='sat'/>"
        "  <feGaussianBlur stdDeviation='1.5' result='blur'/>"
        "  <feBlend mode='multiply' in='sat' in2='blur' result='blended'/>"
        "</filter>"
    )
    service.register_filter("blend", filter_xml)

    results = service.resolve_effects("blend")

    assert len(results) >= 3
    blend_result = results[2]
    assert isinstance(blend_result, FilterEffectResult)
    assert blend_result.fallback == "emf"
    assert isinstance(blend_result.effect, CustomEffect)
    assert blend_result.effect.drawingml.startswith("<a:effectLst>")
    assert blend_result.metadata["inputs"] == ["sat", "blur"]
    assert blend_result.metadata["mode"] == "multiply"
    assert blend_result.metadata["native_support"] is False
    assert blend_result.strategy == "vector"
    assets = blend_result.metadata.get("fallback_assets")
    assert assets and assets[0]["type"] == "emf"
    assert "data_hex" in assets[0]
    assert assets[0].get("metadata", {}).get("filter_type") == "blend"
