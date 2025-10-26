"""Integration tests for resvg-backed style extraction."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.map.converter.core import IRConverter
from svg2ooxml.map.converter import styles_runtime
from svg2ooxml.ir.paint import LinearGradientPaint, SolidPaint
from svg2ooxml.services import configure_services


def _build_converter() -> IRConverter:
    services = configure_services()
    return IRConverter(services=services, logger=None, policy_engine=None, policy_context=None)


def test_extract_style_uses_resvg_gradient_resolution() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="grad1" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stop-color="#000000" stop-opacity="1"/>
                    <stop offset="1" stop-color="#ffffff"/>
                </linearGradient>
            </defs>
            <rect id="rect1" width="10" height="10" fill="url(#grad1)" />
        </svg>
    """

    converter = _build_converter()
    svg_root = etree.fromstring(svg_markup)
    converter._build_resvg_lookup(svg_root)

    rect_element = svg_root.find("{http://www.w3.org/2000/svg}rect")
    assert rect_element is not None

    style = styles_runtime.extract_style(converter, rect_element)
    assert isinstance(style.fill, LinearGradientPaint)
    assert style.fill.gradient_id == "grad1"
    assert len(style.fill.stops) == 2


def test_extract_style_handles_anonymous_solid_fill() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <rect width="10" height="10" fill="#336699" />
        </svg>
    """

    converter = _build_converter()
    svg_root = etree.fromstring(svg_markup)
    converter._build_resvg_lookup(svg_root)

    rect_element = svg_root.find("{http://www.w3.org/2000/svg}rect")
    assert rect_element is not None

    style = styles_runtime.extract_style(converter, rect_element)
    assert isinstance(style.fill, SolidPaint)
    assert style.fill.rgb == "336699".upper()


def test_extract_style_handles_use_expansion() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
            <defs>
                <rect id="shape" width="5" height="5" fill="#ABCDEF" />
            </defs>
            <use xlink:href="#shape" x="2" y="3" />
        </svg>
    """

    svg_root = etree.fromstring(svg_markup)
    converter = _build_converter()
    converter._build_resvg_lookup(svg_root)

    use_element = svg_root.find("{http://www.w3.org/2000/svg}use")
    assert use_element is not None
    assert use_element in converter._resvg_element_lookup

    style = styles_runtime.extract_style(converter, use_element)
    assert isinstance(style.fill, SolidPaint)
    assert style.fill.rgb == "ABCDEF"
