"""Unit tests for paint bridging between resvg and svg2ooxml IR."""

from __future__ import annotations

import pytest

from svg2ooxml.core.resvg.normalizer import normalize_svg_string
from svg2ooxml.ir.paint import LinearGradientPaint, SolidPaint, Stroke
from svg2ooxml.paint.resvg_bridge import resolve_fill_paint, resolve_stroke_style


def _find_rect_node(tree) -> object:
    for child in tree.root.children:
        if getattr(child, "tag", "") == "rect":
            return child
    return None


def test_resolve_paints_for_solid_styles() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <rect width="20" height="10" fill="#336699" stroke="#ff0000" stroke-width="2"/>
        </svg>
    """
    result = normalize_svg_string(svg_markup)
    rect = _find_rect_node(result.tree)
    assert rect is not None, "expected rectangle node in normalized tree"

    fill_paint = resolve_fill_paint(rect.fill, result.tree)
    assert isinstance(fill_paint, SolidPaint)
    assert fill_paint.rgb == "336699"
    assert fill_paint.opacity == pytest.approx(1.0)

    stroke = resolve_stroke_style(rect.stroke, result.tree)
    assert isinstance(stroke, Stroke)
    assert stroke.width == pytest.approx(2.0)
    assert isinstance(stroke.paint, SolidPaint)
    assert stroke.paint.rgb == "FF0000"
    assert stroke.paint.opacity == pytest.approx(1.0)


def test_resolve_paints_for_linear_gradient() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="grad1" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="#000000" stop-opacity="0.5"/>
                    <stop offset="1" stop-color="#ffffff"/>
                </linearGradient>
            </defs>
            <rect width="10" height="10" fill="url(#grad1)"/>
        </svg>
    """
    result = normalize_svg_string(svg_markup)
    rect = _find_rect_node(result.tree)
    assert rect is not None, "expected rectangle node in normalized tree"

    fill_paint = resolve_fill_paint(rect.fill, result.tree)
    assert isinstance(fill_paint, LinearGradientPaint)
    assert fill_paint.gradient_id == "grad1"
    assert fill_paint.start == (0.0, 0.0)
    assert fill_paint.end == (0.0, 1.0)
    assert len(fill_paint.stops) == 2
    assert fill_paint.stops[0].opacity == pytest.approx(0.5)
    assert fill_paint.stops[1].rgb == "FFFFFF"
    transform = fill_paint.transform
    assert transform is not None
    matrix = transform.tolist() if hasattr(transform, "tolist") else transform
    assert matrix[0][0] == pytest.approx(1.0)
    assert matrix[1][1] == pytest.approx(1.0)
