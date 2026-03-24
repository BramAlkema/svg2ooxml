"""Tests ensuring resvg lookup maps DOM elements to expanded resvg nodes."""

from __future__ import annotations

import math

from lxml import etree

from svg2ooxml.core.ir import IRConverter
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.services import configure_services


def _create_converter() -> IRConverter:
    """Create a converter with default services for testing."""
    services = configure_services()
    return IRConverter(services=services)


def _eu_flag_star_ring_svg() -> str:
    return """
        <svg xmlns="http://www.w3.org/2000/svg"
             xmlns:xlink="http://www.w3.org/1999/xlink"
             width="810"
             height="540">
            <defs>
                <g id="s">
                    <g id="c">
                        <path id="t" d="M0,0v1h0.5z" transform="translate(0,-1)rotate(18)" />
                        <use xlink:href="#t" transform="scale(-1,1)" />
                    </g>
                    <g id="a">
                        <use xlink:href="#c" transform="rotate(72)" />
                        <use xlink:href="#c" transform="rotate(144)" />
                    </g>
                    <use xlink:href="#a" transform="scale(-1,1)" />
                </g>
            </defs>
            <g fill="#fc0" transform="scale(30)translate(13.5,9)">
                <use xlink:href="#s" y="-6" />
                <use xlink:href="#s" y="6" />
                <g id="l">
                    <use xlink:href="#s" x="-6" />
                    <use xlink:href="#s" transform="rotate(150)translate(0,6)rotate(66)" />
                    <use xlink:href="#s" transform="rotate(120)translate(0,6)rotate(24)" />
                    <use xlink:href="#s" transform="rotate(60)translate(0,6)rotate(12)" />
                    <use xlink:href="#s" transform="rotate(30)translate(0,6)rotate(42)" />
                </g>
                <use xlink:href="#l" transform="scale(-1,1)" />
            </g>
        </svg>
    """


def _count_path_nodes(node: object) -> int:
    count = 1 if node.__class__.__name__ == "PathNode" else 0
    for child in getattr(node, "children", ()):
        count += _count_path_nodes(child)
    return count


def _collect_star_group_nodes(node: object) -> list[object]:
    if (
        node.__class__.__name__ == "GroupNode"
        and _count_path_nodes(node) == 10
        and getattr(node, "use_source", None) is not None
    ):
        return [node]

    groups: list[object] = []
    for child in getattr(node, "children", ()):
        groups.extend(_collect_star_group_nodes(child))
    return groups


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


def test_resvg_lookup_preserves_distinct_leaf_globals_for_nested_use_chain() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
            <defs>
                <g id="s">
                    <g id="c">
                        <path id="t" d="M0,0v1h0.5z" transform="translate(0,-1)rotate(18)" />
                        <use xlink:href="#t" transform="scale(-1,1)" />
                    </g>
                    <g id="a">
                        <use xlink:href="#c" transform="rotate(72)" />
                        <use xlink:href="#c" transform="rotate(144)" />
                    </g>
                    <use xlink:href="#a" transform="scale(-1,1)" />
                </g>
            </defs>
            <g transform="scale(30)translate(13.5,9)">
                <use xlink:href="#s" y="-6" />
            </g>
        </svg>
    """

    svg_root = etree.fromstring(svg_markup)
    converter = _create_converter()
    converter._build_resvg_lookup(svg_root)

    use_elements = svg_root.xpath(
        ".//svg:use[@y='-6']",
        namespaces={"svg": "http://www.w3.org/2000/svg"},
    )
    assert len(use_elements) == 1

    star_node = converter._resvg_element_lookup[use_elements[0]]
    bridge = converter._resvg_bridge

    def collect_path_nodes(node) -> list[object]:
        paths: list[object] = []
        if node.__class__.__name__ == "PathNode":
            paths.append(node)
        for child in getattr(node, "children", ()):
            paths.extend(collect_path_nodes(child))
        return paths

    leaves = collect_path_nodes(star_node)
    assert len(leaves) == 10

    distinct_globals = {
        (
            round(global_transform.a, 4),
            round(global_transform.b, 4),
            round(global_transform.c, 4),
            round(global_transform.d, 4),
            round(global_transform.e, 4),
            round(global_transform.f, 4),
        )
        for leaf in leaves
        for global_transform in [bridge.node_global_transform_lookup[id(leaf)]]
    }
    assert len(distinct_globals) == 10


def test_resvg_lookup_preserves_eu_flag_ring_star_centers() -> None:
    svg_root = etree.fromstring(_eu_flag_star_ring_svg())
    converter = _create_converter()
    converter._build_resvg_lookup(svg_root)

    bridge = converter._resvg_bridge
    star_groups = _collect_star_group_nodes(bridge.tree.root)
    assert len(star_groups) == 12
    assert all(_count_path_nodes(group) == 10 for group in star_groups)

    observed_centers = sorted(
        (
            round(global_transform.e, 3),
            round(global_transform.f, 3),
        )
        for group in star_groups
        for global_transform in [bridge.node_global_transform_lookup[id(group)]]
    )

    expected_centers = sorted(
        (
            round(405.0 + 180.0 * math.cos(math.radians(angle)), 3),
            round(270.0 + 180.0 * math.sin(math.radians(angle)), 3),
        )
        for angle in range(-90, 270, 30)
    )

    assert observed_centers == expected_centers
