"""Tests for drop shadow and glow filter primitives."""

from __future__ import annotations

from lxml import etree

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
    assert first.strategy == "native"
    assert isinstance(first.effect, CustomEffect)
    assert "outerShdw" in first.effect.drawingml
    assert first.metadata["std_dev"] == 1.2


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
    assert first.strategy == "native"
    assert isinstance(first.effect, CustomEffect)
    assert "<a:glow" in first.effect.drawingml
