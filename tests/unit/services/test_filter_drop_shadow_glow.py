"""Tests for drop shadow and glow filter primitives."""

from __future__ import annotations

from lxml import etree
from tests.unit.filters.policy import assert_fallback, assert_strategy

from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.services.filter_service import FilterService
from svg2ooxml.services.filter_types import FilterEffectResult


def test_drop_shadow_native() -> None:
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='shadow'><feDropShadow dx='2' dy='3' stdDeviation='1.2' flood-color='#112233' flood-opacity='0.5'/></filter>"
    )
    service.register_filter("shadow", filter_xml)

    results = service.resolve_effects("shadow")

    assert results
    first = results[0]
    assert isinstance(first, FilterEffectResult)
    assert_strategy(first, modern="native")
    assert_fallback(first, modern=None)
    assert isinstance(first.effect, CustomEffect)
    assert "outerShdw" in first.effect.drawingml
    assert first.metadata["std_dev"] == 1.2


def test_drop_shadow_resolves_named_color_and_percentage_opacity() -> None:
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='shadow'><feDropShadow dx='2' dy='3' stdDeviation='1' flood-color='rebeccapurple' flood-opacity='25%'/></filter>"
    )
    service.register_filter("shadow", filter_xml)

    result = service.resolve_effects("shadow")[0]

    assert result.metadata["color"] == "663399"
    assert result.metadata["opacity"] == 0.25
    assert '<a:srgbClr val="663399">' in result.effect.drawingml
    assert '<a:alpha val="25000"/>' in result.effect.drawingml


def test_glow_native() -> None:
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='glow'><feGlow stdDeviation='4' flood-color='#abcdef' flood-opacity='0.7'/></filter>"
    )
    service.register_filter("glow", filter_xml)

    results = service.resolve_effects("glow")

    assert results
    first = results[0]
    assert isinstance(first, FilterEffectResult)
    assert_strategy(first, modern="native")
    assert_fallback(first, modern=None)
    assert isinstance(first.effect, CustomEffect)
    assert "<a:glow" in first.effect.drawingml


def test_glow_resolves_named_color_and_percentage_opacity() -> None:
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='glow'><feGlow stdDeviation='4' flood-color='blue' flood-opacity='75%'/></filter>"
    )
    service.register_filter("glow", filter_xml)

    result = service.resolve_effects("glow")[0]

    assert result.metadata["color"] == "0000FF"
    assert result.metadata["opacity"] == 0.75
    assert '<a:srgbClr val="0000FF">' in result.effect.drawingml
    assert '<a:alpha val="75000"/>' in result.effect.drawingml
