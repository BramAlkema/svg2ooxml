"""Tests for parser style context helpers."""

from lxml import etree

from svg2ooxml.parser.style_context import build_style_context, resolve_viewport
from svg2ooxml.parser.units import UnitConverter


def test_resolve_viewport_uses_explicit_dimensions() -> None:
    svg = etree.fromstring("<svg width='200' height='100' />")

    width, height = resolve_viewport(svg, UnitConverter())
    assert width == 200.0
    assert height == 100.0


def test_resolve_viewport_falls_back_to_viewbox() -> None:
    svg = etree.fromstring("<svg viewBox='0 0 400 300' />")

    width, height = resolve_viewport(svg, UnitConverter())

    assert width == 400.0
    assert height == 300.0


def test_build_style_context_creates_conversion_context() -> None:
    svg = etree.fromstring("<svg width='200' height='100' />")

    style_ctx = build_style_context(svg, UnitConverter())

    assert style_ctx.viewport_width == 200.0
    assert style_ctx.viewport_height == 100.0
    assert style_ctx.conversion.width == 200.0
    assert style_ctx.conversion.height == 100.0
    assert style_ctx.conversion.font_size == 12.0
