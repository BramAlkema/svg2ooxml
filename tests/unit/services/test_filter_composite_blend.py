"""Tests for composite and blend filter primitives."""

from __future__ import annotations

from lxml import etree
from tests.unit.filters.policy import assert_assets, assert_fallback, assert_strategy

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
    assert_fallback(first, modern="emf")
    assert isinstance(first.effect, CustomEffect)
    assert first.metadata["operator"] == "arithmetic"
    assert "k1" in first.metadata
    assert_assets(first, modern="emf")


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
    assert_fallback(composite, modern=None)
    assert isinstance(composite.effect, CustomEffect)
    assert composite.effect.drawingml.startswith("<a:effectLst>")
    assert composite.metadata["inputs"] == ["blurred"]
    assert composite.metadata["operator"] == "over"
    assert composite.metadata.get("native_support") is True
    assert "fallback_assets" not in composite.metadata or not composite.metadata["fallback_assets"]


def test_composite_in_uses_effect_dag_when_policy_enabled() -> None:
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='comp'>"
        "  <feFlood flood-color='#FF0000' flood-opacity='0.7' result='mask'/>"
        "  <feComposite operator='in' in='SourceGraphic' in2='mask' result='masked'/>"
        "</filter>"
    )
    service.register_filter("comp", filter_xml)

    results = service.resolve_effects(
        "comp",
        context={"policy": {"enable_effect_dag": True}},
    )

    assert len(results) >= 2
    composite = results[1]
    assert isinstance(composite, FilterEffectResult)
    assert_fallback(composite, modern=None)
    assert composite.effect.drawingml.startswith("<a:effectDag>")
    assert "<a:alphaModFix>" in composite.effect.drawingml
    assert composite.metadata["operator"] == "in"
    assert composite.metadata.get("native_support") is True


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
    assert_fallback(first, modern="bitmap", legacy="emf")
    assert_strategy(first, modern="raster", legacy="vector")
    assert isinstance(first.effect, CustomEffect)
    assert first.metadata["mode"] == "multiply"
    assert_assets(first, modern="raster", legacy="emf")


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
    assert_fallback(blend_result, modern="bitmap", legacy="emf")
    assert isinstance(blend_result.effect, CustomEffect)
    assert blend_result.effect.drawingml.startswith("<a:effectLst>")
    assert blend_result.metadata["inputs"] == ["sat", "blur"]
    assert blend_result.metadata["mode"] == "multiply"
    assert blend_result.metadata["native_support"] is False
    assert_strategy(blend_result, modern="raster", legacy="vector")
    assert_assets(blend_result, modern="raster", legacy="emf")
