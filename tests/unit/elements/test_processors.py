"""Regression tests for the richer element processors."""

from __future__ import annotations

import base64

from lxml import etree

from svg2ooxml.elements import (
    create_gradient_processor,
    create_image_processor,
    create_pattern_processor,
)
from svg2ooxml.services import configure_services


def _services():
    return configure_services()


def test_gradient_processor_produces_analysis() -> None:
    services = _services()
    processor = create_gradient_processor(services)
    gradient_xml = etree.fromstring(
        """
        <linearGradient id="g1">
            <stop offset="0%" stop-color="#000000"/>
            <stop offset="100%" stop-color="#ffffff"/>
        </linearGradient>
        """
    )

    analysis = processor.analyze_gradient_element(gradient_xml, context=None)

    assert analysis.stop_count == 2
    assert analysis.gradient_type == "linearGradient"
    assert processor.get_processing_statistics()["gradients_analyzed"] == 1

    processor.analyze_gradient_element(gradient_xml, context=None)
    assert processor.get_processing_statistics()["cache_hits"] == 1


def test_pattern_processor_detects_grid() -> None:
    services = _services()
    processor = create_pattern_processor(services)
    pattern_xml = etree.fromstring(
        """
        <pattern id="p1" width="10" height="10" patternUnits="userSpaceOnUse">
            <rect x="0" y="0" width="10" height="2" fill="#333"/>
            <rect x="0" y="4" width="10" height="2" fill="#333"/>
            <rect x="0" y="8" width="10" height="2" fill="#333"/>
            <rect x="0" y="0" width="2" height="10" fill="#333"/>
            <rect x="4" y="0" width="2" height="10" fill="#333"/>
            <rect x="8" y="0" width="2" height="10" fill="#333"/>
        </pattern>
        """
    )

    analysis = processor.analyze_pattern_element(pattern_xml, context=None)

    assert analysis.pattern_type.name in {"GRID", "CROSS"}
    assert analysis.child_count == 6


def test_image_processor_handles_data_uri() -> None:
    services = _services()
    processor = create_image_processor(services)
    payload = base64.b64encode(b"fakepngdata").decode("ascii")
    image_xml = etree.fromstring(
        f'<image width="10" height="5" href="data:image/png;base64,{payload}"/>'
    )

    analysis = processor.analyze_image_element(image_xml, context=None)

    assert analysis.is_embedded is True
    assert analysis.format.name == "PNG"
