"""Tests for the Gaussian blur filter primitive."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.services.filter_service import FilterService
from svg2ooxml.services.filter_types import FilterEffectResult


def test_gaussian_blur_native_support() -> None:
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='blur'><feGaussianBlur stdDeviation='2'/></filter>"
    )
    service.register_filter("blur", filter_xml)

    results = service.resolve_effects("blur")

    assert results
    first = results[0]
    assert isinstance(first, FilterEffectResult)
    assert first.strategy == "native"
    assert isinstance(first.effect, CustomEffect)
    assert "<a:blur" in first.effect.drawingml


def test_gaussian_blur_anisotropic_fallback() -> None:
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='blur'><feGaussianBlur stdDeviation='2 4'/></filter>"
    )
    service.register_filter("blur", filter_xml)

    results = service.resolve_effects("blur")

    assert results
    first = results[0]
    assert first.strategy in {"native", "raster"}
    assert first.effect is not None
    assert first.metadata["std_deviation_x"] == 2.0
    assert first.metadata["std_deviation_y"] == 4.0


def test_gaussian_blur_anisotropic_with_policy_native() -> None:
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='blur'><feGaussianBlur stdDeviation='2 4'/></filter>"
    )
    service.register_filter("blur", filter_xml)

    results = service.resolve_effects("blur", context={"policy": {"allow_anisotropic_native": True}})

    assert results
    first = results[0]
    assert first.strategy == "native"
    assert isinstance(first.effect, CustomEffect)
    assert "blur" in first.effect.drawingml
    assert first.metadata.get("anisotropic_mode") == "approx_native"
