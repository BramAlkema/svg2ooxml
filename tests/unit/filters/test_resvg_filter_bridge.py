"""Ensure resvg filter nodes convert into svg2ooxml descriptors."""

from __future__ import annotations

from svg2ooxml.core.resvg.normalizer import normalize_svg_string
from svg2ooxml.filters.resvg_bridge import (
    resolve_filter_element,
    resolve_filter_node,
    resolve_filter_reference,
)


def _find_rect_with_filter(tree) -> object:
    for child in tree.root.children:
        if getattr(child, "tag", "") == "rect" and "filter" in child.attributes:
            return child
    return None


def test_resolve_filter_reference_collects_primitives() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <defs>
                <filter id="f1" filterUnits="userSpaceOnUse" primitiveUnits="userSpaceOnUse">
                    <feGaussianBlur stdDeviation="3"/>
                    <feOffset dx="2" dy="1"/>
                </filter>
            </defs>
            <rect width="10" height="10" filter="url(#f1)"/>
        </svg>
    """
    result = normalize_svg_string(svg_markup)
    rect = _find_rect_with_filter(result.tree)
    assert rect is not None, "expected rectangle with filter attribute"

    resolved = resolve_filter_reference(rect.attributes.get("filter"), result.tree)
    assert resolved is not None
    assert resolved.filter_id == "f1"
    assert [primitive.tag for primitive in resolved.primitives] == ["feGaussianBlur", "feOffset"]
    assert resolved.filter_units == "userSpaceOnUse"
    assert resolved.primitive_units == "userSpaceOnUse"

    direct = resolve_filter_node(result.tree.filters["f1"])
    assert direct == resolved


def test_resolve_filter_element_resolves_lighting_current_color_from_ancestors() -> None:
    svg_markup = """
        <svg xmlns="http://www.w3.org/2000/svg">
            <defs color="#00FF00">
                <filter id="greenLight">
                    <feDiffuseLighting lighting-color="currentColor">
                        <feDistantLight azimuth="0" elevation="90"/>
                    </feDiffuseLighting>
                </filter>
            </defs>
        </svg>
    """
    root = normalize_svg_string(svg_markup).document.root.source
    filter_element = root.xpath(
        ".//*[local-name()='filter' and @id='greenLight']"
    )[0]

    resolved = resolve_filter_element(filter_element)

    primitive = resolved.primitives[0]
    assert primitive.attributes["lighting-color"] == "#00FF00"
    assert primitive.extras["lighting_color"] == "#00FF00"
