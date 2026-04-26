"""Smoke tests for the resvg-backed normalizer stage."""

from __future__ import annotations

import pytest

from svg2ooxml.core.resvg.normalizer import NormalizationResult, normalize_svg_string
from svg2ooxml.core.resvg.painting.paint import PaintReference


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


def test_resvg_tree_resolves_percentage_geometry_against_viewport() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
            <rect x="10%" y="20%" width="50%" height="25%"/>
        </svg>
    """

    result = normalize_svg_string(svg_markup)
    rect = next(child for child in result.tree.root.children if child.tag == "rect")

    assert rect.x == pytest.approx(20.0)
    assert rect.y == pytest.approx(20.0)
    assert rect.width == pytest.approx(100.0)
    assert rect.height == pytest.approx(25.0)


def test_resvg_tree_resolves_geometry_absolute_units() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" width="2in" height="72pt">
            <line x1="0.25in" y1="12pt" x2="50%" y2="100%"/>
        </svg>
    """

    result = normalize_svg_string(svg_markup)
    line = next(child for child in result.tree.root.children if child.tag == "line")

    assert line.x1 == pytest.approx(24.0)
    assert line.y1 == pytest.approx(16.0)
    assert line.x2 == pytest.approx(96.0)
    assert line.y2 == pytest.approx(96.0)


def test_resvg_presentation_resolves_absolute_stroke_lengths() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
            <rect width="10" height="10"
                  stroke="#000000" stroke-width="0.25in" stroke-dashoffset="6pt"/>
        </svg>
    """

    result = normalize_svg_string(svg_markup)
    rect = next(child for child in result.tree.root.children if child.tag == "rect")

    assert rect.stroke is not None
    assert rect.stroke.width == pytest.approx(24.0)
    assert rect.stroke.dash_offset == pytest.approx(8.0)


def test_resvg_stroke_dasharray_resolves_absolute_lengths() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
            <rect width="10" height="10"
                  stroke="#000000" stroke-width="1"
                  stroke-dasharray="0.25in 6pt"/>
        </svg>
    """

    result = normalize_svg_string(svg_markup)
    rect = next(child for child in result.tree.root.children if child.tag == "rect")

    assert rect.stroke is not None
    assert rect.stroke.dash_array == pytest.approx([24.0, 8.0])


def test_resvg_tree_resolves_image_geometry_units() -> None:
    png_data = (
        "iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAYAAAC09K7GAAAAFUlEQVR4nGP8z8DwnwEJ"
        "MCFzsAoAAGFrAgT6YybLAAAAAElFTkSuQmCC"
    )
    svg_markup = f"""
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
            <image href="data:image/png;base64,{png_data}"
                   x="10%" y="20%" width="50%" height="25%"/>
        </svg>
    """

    result = normalize_svg_string(svg_markup)
    image = next(child for child in result.tree.root.children if child.tag == "image")

    assert image.x == pytest.approx(20.0)
    assert image.y == pytest.approx(20.0)
    assert image.width == pytest.approx(100.0)
    assert image.height == pytest.approx(25.0)
    assert image.data is not None


def test_resvg_tree_resolves_userspace_gradient_units() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
            <defs>
                <linearGradient id="grad" gradientUnits="userSpaceOnUse"
                                x1="0.25in" y1="6pt">
                    <stop offset="0" stop-color="#000000"/>
                    <stop offset="1" stop-color="#ffffff"/>
                </linearGradient>
            </defs>
            <rect width="100" height="50" fill="url(#grad)"/>
        </svg>
    """

    result = normalize_svg_string(svg_markup)
    gradient_node = result.tree.paint_servers["grad"]
    gradient = gradient_node.gradient

    assert gradient is not None
    assert gradient.units == "userSpaceOnUse"
    assert gradient.x1 == pytest.approx(24.0)
    assert gradient.y1 == pytest.approx(8.0)
    assert gradient.x2 == pytest.approx(200.0)
    assert gradient.y2 == pytest.approx(0.0)


def test_resvg_gradient_inheritance_reinterprets_coordinates_in_effective_units() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
            <defs>
                <linearGradient id="base" x2="100%">
                    <stop offset="0" stop-color="#000000"/>
                    <stop offset="1" stop-color="#ffffff"/>
                </linearGradient>
                <linearGradient id="child" href="#base" gradientUnits="userSpaceOnUse"
                                x1="0.25in"/>
            </defs>
            <rect width="100" height="50" fill="url(#child)"/>
        </svg>
    """

    result = normalize_svg_string(svg_markup)
    gradient = result.tree.resolve_paint(PaintReference("#child"))

    assert gradient is not None
    assert gradient.units == "userSpaceOnUse"
    assert gradient.x1 == pytest.approx(24.0)
    assert gradient.x2 == pytest.approx(200.0)


def test_resvg_tree_resolves_relative_font_size_against_parent() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
            <g font-size="20pt">
                <text font-size="150%">Hello</text>
            </g>
        </svg>
    """

    result = normalize_svg_string(svg_markup)
    group = next(child for child in result.tree.root.children if child.tag == "g")
    text = next(child for child in group.children if child.tag == "text")

    assert group.text_style is not None
    assert group.text_style.font_size == pytest.approx(20.0)
    assert text.text_style is not None
    assert text.text_style.font_size == pytest.approx(30.0)


def test_resvg_stylesheet_important_beats_more_specific_normal_rule() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
            <style>
                rect { fill: #008000 !important; }
                #target { fill: #ff0000; }
            </style>
            <rect id="target" width="10" height="10"/>
        </svg>
    """

    result = normalize_svg_string(svg_markup)
    rect = next(child for child in result.tree.root.children if child.tag == "rect")

    assert rect.fill is not None and rect.fill.color is not None
    assert (rect.fill.color.r, rect.fill.color.g, rect.fill.color.b) == pytest.approx(
        (0.0, 128 / 255, 0.0)
    )


def test_resvg_stylesheet_important_beats_inline_normal_rule() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
            <style>rect { fill: #008000 !important; }</style>
            <rect width="10" height="10" style="fill: #ff0000"/>
        </svg>
    """

    result = normalize_svg_string(svg_markup)
    rect = next(child for child in result.tree.root.children if child.tag == "rect")

    assert rect.fill is not None and rect.fill.color is not None
    assert (rect.fill.color.r, rect.fill.color.g, rect.fill.color.b) == pytest.approx(
        (0.0, 128 / 255, 0.0)
    )


def test_resvg_inline_important_overrides_stylesheet_important() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">
            <style>rect { fill: #008000 !important; }</style>
            <rect width="10" height="10" style="fill: #ff0000 !important"/>
        </svg>
    """

    result = normalize_svg_string(svg_markup)
    rect = next(child for child in result.tree.root.children if child.tag == "rect")

    assert rect.fill is not None and rect.fill.color is not None
    assert (rect.fill.color.r, rect.fill.color.g, rect.fill.color.b) == pytest.approx(
        (1.0, 0.0, 0.0)
    )


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
