from __future__ import annotations

import pytest

pytest.importorskip("numpy")

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.render.normalize import normalize_svg
from svg2ooxml.render.paint import LinearGradient


def test_normalize_builds_tree_with_transforms():
    svg_markup = """
    <svg xmlns=\"http://www.w3.org/2000/svg\" width=\"100\" height=\"50\">
        <g transform=\"translate(10,5)\">
            <rect id=\"rect1\" width=\"20\" height=\"10\" />
        </g>
    </svg>
    """
    root = etree.fromstring(svg_markup)

    tree = normalize_svg(root)

    assert tree.viewport_width == 100
    assert tree.viewport_height == 50

    # Root node
    assert tree.root.tag == "svg"
    assert tree.root.local_transform == Matrix2D.identity()

    # Group node
    group_node = tree.root.children[0]
    assert group_node.tag == "g"
    assert group_node.local_transform.e == 10
    assert group_node.local_transform.f == 5

    # Rect node inherits transform
    rect_element = group_node.children[0].source
    rect_node = tree.node_index[id(rect_element)]
    assert rect_node.tag == "rect"
    assert rect_node.local_transform == Matrix2D.identity()
    assert rect_node.world_transform.e == 10
    assert rect_node.world_transform.f == 5
    rect_geometry = rect_node.geometry
    assert rect_geometry is not None
    assert rect_geometry.bounds.width == 20

    fill = rect_node.fill
    assert fill is None


def test_normalize_resolves_fill_and_stroke():
    svg_markup = """
    <svg xmlns=\"http://www.w3.org/2000/svg\">
        <rect width=\"10\" height=\"5\" fill=\"#336699\" stroke=\"#ff0000\" stroke-width=\"2\" />
    </svg>
    """
    root = etree.fromstring(svg_markup)
    tree = normalize_svg(root)

    rect_node = tree.root.children[0]
    fill = rect_node.fill
    assert fill is not None
    assert tuple(round(component, 4) for component in fill.color) == (0.2, 0.4, 0.6)

    stroke = rect_node.stroke
    assert stroke is not None
    assert stroke.width == 2
    assert stroke.paint is not None
    assert tuple(round(component, 4) for component in stroke.paint.color) == (1.0, 0.0, 0.0)


def test_normalize_resolves_geometry_length_units():
    svg_markup = """
    <svg xmlns=\"http://www.w3.org/2000/svg\" width=\"200\" height=\"100\">
        <rect x=\"10%\" y=\"1cm\" width=\"2cm\" height=\"25%\" />
    </svg>
    """
    root = etree.fromstring(svg_markup)

    tree = normalize_svg(root)

    rect_node = tree.root.children[0]
    rect_geometry = rect_node.geometry
    assert rect_geometry.bounds.x == pytest.approx(20.0)
    assert rect_geometry.bounds.y == pytest.approx(37.7952755906)
    assert rect_geometry.bounds.width == pytest.approx(75.5905511811)
    assert rect_geometry.bounds.height == pytest.approx(25.0)


def test_normalize_handles_gradients():
    svg_markup = """
    <svg xmlns=\"http://www.w3.org/2000/svg\" width=\"10\" height=\"10\">
      <defs>
        <linearGradient id=\"grad1\" x1=\"0\" y1=\"0\" x2=\"10\" y2=\"0\" gradientUnits=\"userSpaceOnUse\">
          <stop offset=\"0%\" stop-color=\"#000000\" />
          <stop offset=\"100%\" stop-color=\"#ffffff\" />
        </linearGradient>
      </defs>
      <rect width=\"10\" height=\"10\" fill=\"url(#grad1)\" />
    </svg>
    """
    root = etree.fromstring(svg_markup)
    tree = normalize_svg(root)

    rect_node = tree.root.children[1]
    fill = rect_node.fill
    assert isinstance(fill, LinearGradient)
    assert fill.start == (0.0, 0.0)
    assert fill.end == (10.0, 0.0)
    assert len(fill.stops) == 2


def test_normalize_preserves_case_sensitive_paint_url_ids():
    svg_markup = """
    <svg xmlns=\"http://www.w3.org/2000/svg\" width=\"10\" height=\"10\">
      <defs>
        <linearGradient id=\"GradA\">
          <stop offset=\"0\" stop-color=\"red\"
                style=\"stop-color: rgb(0 0 255 / 75%); stop-opacity: 50%\"/>
          <stop offset=\"1\" stop-color=\"blue\"/>
        </linearGradient>
      </defs>
      <rect width=\"10\" height=\"10\" fill=\"url(#GradA)\" fill-opacity=\"50%\" />
    </svg>
    """
    root = etree.fromstring(svg_markup)

    tree = normalize_svg(root)

    fill = tree.root.children[1].fill
    assert isinstance(fill, LinearGradient)
    assert fill.stops[0].color == pytest.approx((0.0, 0.0, 1.0))
    assert [stop.opacity for stop in fill.stops] == pytest.approx([0.1875, 0.5])


def test_normalize_resolves_css_color_alpha_and_current_color():
    svg_markup = """
    <svg xmlns=\"http://www.w3.org/2000/svg\" width=\"10\" height=\"10\" color=\"rebeccapurple\">
      <rect width=\"10\" height=\"10\"
            fill=\"currentColor\"
            stroke=\"rgb(0 0 255 / 75%)\"
            stroke-opacity=\"50%\" />
    </svg>
    """
    root = etree.fromstring(svg_markup)

    tree = normalize_svg(root)

    rect_node = tree.root.children[0]
    assert rect_node.fill.color == pytest.approx((0.4, 0.2, 0.6))
    assert rect_node.fill.opacity == pytest.approx(1.0)
    assert rect_node.stroke.paint.color == pytest.approx((0.0, 0.0, 1.0))
    assert rect_node.stroke.paint.opacity == pytest.approx(0.375)


def test_normalize_parses_compact_signed_poly_points():
    svg_markup = """
    <svg xmlns=\"http://www.w3.org/2000/svg\" width=\"20\" height=\"20\">
      <polyline points=\"0,0 10-5 20,0\" />
    </svg>
    """
    root = etree.fromstring(svg_markup)

    tree = normalize_svg(root)

    geometry = tree.root.children[0].geometry
    assert geometry["points"] == [(0.0, 0.0), (10.0, -5.0), (20.0, 0.0)]


def test_normalize_rect_explicit_zero_radius_stays_square():
    svg_markup = """
    <svg xmlns=\"http://www.w3.org/2000/svg\" width=\"20\" height=\"20\">
      <rect width=\"10\" height=\"10\" rx=\"0\" ry=\"5\" />
    </svg>
    """
    root = etree.fromstring(svg_markup)

    tree = normalize_svg(root)

    assert tree.root.children[0].geometry.corner_radius == 0.0
