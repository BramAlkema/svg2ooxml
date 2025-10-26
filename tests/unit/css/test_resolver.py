"""Tests for the CSS style resolver."""

import pytest
from lxml import etree

from svg2ooxml.css import StyleContext, StyleResolver
from svg2ooxml.parser.units import UnitConverter


def _make_context(width: float = 200.0, height: float = 100.0) -> tuple[UnitConverter, StyleContext]:
    converter = UnitConverter()
    conversion = converter.create_context(
        width=width,
        height=height,
        font_size=12.0,
        parent_width=width,
        parent_height=height,
    )
    return converter, StyleContext(conversion=conversion, viewport_width=width, viewport_height=height)


def test_style_resolver_applies_attributes() -> None:
    resolver = StyleResolver()
    element = etree.fromstring(
        "<text font-family='Calibri' font-size='16pt' font-weight='700'>Hello</text>"
    )

    style = resolver.compute_text_style(element)

    assert style["font_family"] == "Calibri"
    assert style["font_size_pt"] == pytest.approx(16.0)
    assert style["font_weight"] == "bold"


def test_style_resolver_parses_inline_styles() -> None:
    resolver = StyleResolver()
    element = etree.fromstring(
        "<text style='font-style: italic; fill: #ff0000'>Hello</text>"
    )

    style = resolver.compute_text_style(element)

    assert style["font_style"] == "italic"
    assert style["fill"] == "#FF0000"


def test_style_resolver_supports_percentage_font_size() -> None:
    resolver = StyleResolver()
    parent = resolver.default_text_style()
    parent["font_size_pt"] = 10.0
    element = etree.fromstring("<text style='font-size: 150%'>Hello</text>")

    style = resolver.compute_text_style(element, parent_style=parent)

    assert style["font_size_pt"] == pytest.approx(15.0)


def test_style_resolver_resolves_current_color() -> None:
    resolver = StyleResolver()
    parent = resolver.default_text_style()
    parent["fill"] = "#112233"
    element = etree.fromstring("<text style='fill: currentColor'>Hello</text>")

    style = resolver.compute_text_style(element, parent_style=parent)

    assert style["fill"] == "#112233"


def test_paint_style_handles_url_and_percentage_width() -> None:
    resolver = StyleResolver()
    _, context = _make_context(width=200.0, height=100.0)
    element = etree.fromstring(
        "<rect fill='url(#grad)' stroke='none' stroke-width='50%' opacity='0.5'/>"
    )

    paint = resolver.compute_paint_style(element, context=context)

    assert paint["fill"] == "url(#grad)"
    assert paint["stroke"] is None
    assert paint["stroke_width_px"] == pytest.approx(100.0)
    assert paint["opacity"] == pytest.approx(0.5)
