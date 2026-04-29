"""Regression tests for the richer element processors."""

from __future__ import annotations

import base64

import pytest
from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.elements import (
    create_gradient_processor,
    create_image_processor,
    create_pattern_processor,
)
from svg2ooxml.elements.patterns.tile_renderer import (
    path_ellipse_geometry,
    tile_ellipse_geometry,
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


def test_pattern_processor_resolves_calc_dimensions() -> None:
    services = _services()
    processor = create_pattern_processor(services)
    pattern_xml = etree.fromstring(
        """
        <pattern id="p1" width="calc(25% + 25%)" height="calc(0.25in + 6pt)">
            <rect width="5" height="5" fill="#112233"/>
        </pattern>
        """
    )

    analysis = processor.analyze_pattern_element(pattern_xml, context=None)

    assert analysis.geometry.tile_width == pytest.approx(0.5)
    assert analysis.geometry.tile_height == pytest.approx(32.0)


def test_pattern_processor_classifies_calc_rect_lines() -> None:
    services = _services()
    processor = create_pattern_processor(services)
    pattern_xml = etree.fromstring(
        """
        <pattern id="lines" width="10" height="10" patternUnits="userSpaceOnUse">
            <rect width="calc(8 + 2)" height="2" fill="#333"/>
        </pattern>
        """
    )

    analysis = processor.analyze_pattern_element(pattern_xml, context=None)

    assert analysis.pattern_type.name == "LINES"


def test_pattern_processor_presets_calc_line_orientation() -> None:
    services = _services()
    processor = create_pattern_processor(services)
    pattern_xml = etree.fromstring(
        """
        <pattern id="vertical" width="10" height="10" patternUnits="userSpaceOnUse">
            <line x1="0" y1="0" x2="0" y2="calc(8 + 2)" stroke="#333"/>
        </pattern>
        """
    )

    analysis = processor.analyze_pattern_element(pattern_xml, context=None)

    assert analysis.pattern_type.name == "LINES"
    assert analysis.preset_candidate == "vert"


def test_pattern_processor_detects_grouped_arc_dots_from_style() -> None:
    services = _services()
    processor = create_pattern_processor(services)
    pattern_xml = etree.fromstring(
        """
        <pattern id="dots" width="8" height="7" patternUnits="userSpaceOnUse"
                 patternTransform="translate(12,4)">
            <g transform="translate(-12,-4)">
                <rect width="8" height="7" style="fill:none;stroke:none"/>
                <path
                    sodipodi:type="arc"
                    xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
                    style="fill:#000000;stroke:none"
                    d="M 10,10 A 3,3 0 1 1 10,9.99"/>
                <path
                    sodipodi:type="arc"
                    xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
                    style="fill:#000000;stroke:none"
                    d="M 10,10 A 3,3 0 1 1 10,9.99"/>
                <path
                    sodipodi:type="arc"
                    xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
                    style="fill:#000000;stroke:none"
                    d="M 10,10 A 3,3 0 1 1 10,9.99"/>
                <path
                    sodipodi:type="arc"
                    xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
                    style="fill:#000000;stroke:none"
                    d="M 10,10 A 3,3 0 1 1 10,9.99"/>
            </g>
        </pattern>
        """
    )

    analysis = processor.analyze_pattern_element(pattern_xml, context=None)

    assert analysis.pattern_type.name == "DOTS"
    assert analysis.child_count == 4
    assert analysis.preset_candidate is not None
    assert analysis.powerpoint_compatible is True
    assert analysis.emf_fallback_recommended is False
    assert analysis.colors_used == ["#000000"]


def test_tile_ellipse_geometry_resolves_calc_circle_attrs() -> None:
    circle = etree.fromstring(
        '<circle cx="calc(2 + 3)" cy="calc(4 + 1)" r="calc(1 + 2)" fill="#000"/>'
    )

    geometry = tile_ellipse_geometry(circle, Matrix2D.identity())

    assert geometry == pytest.approx((5.0, 5.0, 3.0, 3.0))


def test_path_ellipse_geometry_uses_shared_numeric_path_parser() -> None:
    path = etree.fromstring(
        '<path style="fill:#000" d="M10,10A3,3 0 1 1 10,9.99"/>'
    )

    geometry = path_ellipse_geometry(path)

    assert geometry == pytest.approx((7.0, 10.0, 3.0, 3.0))


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
