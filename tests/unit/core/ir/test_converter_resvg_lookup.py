"""Tests ensuring resvg lookup maps DOM elements to expanded resvg nodes."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.core.ir import IRConverter
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.services import configure_services


def _create_converter() -> IRConverter:
    """Create a converter with default services for testing."""
    services = configure_services()
    return IRConverter(services=services)


def test_use_element_maps_to_expanded_rect_with_stroke_width() -> None:
    """<use> elements should resolve to cloned resvg nodes carrying stroke widths."""
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
            <defs>
                <rect id="base-rect" width="10" height="10" />
            </defs>
            <use id="instance"
                 xlink:href="#base-rect"
                 stroke="darkgreen"
                 stroke-width="10" />
        </svg>
    """

    svg_root = etree.fromstring(svg_markup)
    converter = _create_converter()
    converter._build_resvg_lookup(svg_root)

    use_element = svg_root.find("{http://www.w3.org/2000/svg}use")
    assert use_element is not None
    assert use_element in converter._resvg_element_lookup

    resvg_node = converter._resvg_element_lookup[use_element]
    assert resvg_node.__class__.__name__ == "RectNode"

    stroke = getattr(resvg_node, "stroke", None)
    assert stroke is not None
    # usvg resolves stroke-width into device units (user units here)
    assert stroke.width == 10.0


def test_expand_use_noop_when_resvg_available() -> None:
    """expand_use should not mutate DOM when resvg mapping exists."""
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
            <defs>
                <rect id="base-rect" width="10" height="10" />
            </defs>
            <use id="instance"
                 xlink:href="#base-rect"
                 stroke="darkgreen"
                 stroke-width="10" />
        </svg>
    """

    svg_root = etree.fromstring(svg_markup)
    converter = _create_converter()
    converter._policy_context = {"geometry": {"geometry_mode": "resvg"}}

    converter._build_resvg_lookup(svg_root)

    use_element = svg_root.find("{http://www.w3.org/2000/svg}use")
    assert use_element is not None
    assert converter._can_use_resvg(use_element) is True

    coord_space = CoordinateSpace()
    result = converter.expand_use(
        element=use_element,
        coord_space=coord_space,
        current_navigation=None,
        traverse_callback=lambda node, nav: [],
    )

    assert result == []
    # DOM element should remain a <use>
    assert use_element.tag.endswith("use")
