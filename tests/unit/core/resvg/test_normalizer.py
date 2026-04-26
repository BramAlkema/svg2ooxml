"""Smoke tests for the resvg-backed normalizer stage."""

from __future__ import annotations

import pytest

from svg2ooxml.core.resvg.normalizer import NormalizationResult, normalize_svg_string


def test_normalize_svg_string_round_trips_basic_tree() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
            <rect id="box" x="1" y="2" width="3" height="4" fill="#ff0000"/>
        </svg>
    """

    result = normalize_svg_string(svg_markup)
    assert isinstance(result, NormalizationResult)
    assert result.document.root.tag.endswith("svg")
    rect = next(
        (child for child in result.tree.root.children if child.tag.endswith("rect")),
        None,
    )
    assert rect is not None, "expected rectangle node to be present"
    assert rect.fill is not None and rect.fill.color is not None
    assert rect.attributes["width"] == "3"


def test_resvg_tree_parses_compact_signed_points() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">
            <polyline points="0,0 10-5 20,0"/>
        </svg>
    """

    result = normalize_svg_string(svg_markup)
    poly = next(child for child in result.tree.root.children if child.tag == "polyline")

    assert poly.points == (0.0, 0.0, 10.0, -5.0, 20.0, 0.0)


def test_resvg_gradient_stop_style_overrides_attributes() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">
          <defs>
            <linearGradient id="g">
              <stop offset="0" stop-color="red" stop-opacity="1"
                    style="stop-color: rgb(0 0 255 / 75%); stop-opacity: 50%"/>
            </linearGradient>
          </defs>
          <rect width="20" height="20" fill="url(#g)"/>
        </svg>
    """

    result = normalize_svg_string(svg_markup)
    gradient = result.tree.paint_servers["g"].gradient
    stop = gradient.stops[0]

    assert (stop.color.r, stop.color.g, stop.color.b) == pytest.approx((0.0, 0.0, 1.0))
    assert stop.color.a == pytest.approx(0.375)
