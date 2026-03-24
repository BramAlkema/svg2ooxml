"""Regression tests for legacy DOM ``<use>`` expansion helpers."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.common.geometry import parse_transform_list
from svg2ooxml.core.ir import IRConverter
from svg2ooxml.core.parser import ParseResult
from svg2ooxml.core.styling.use_expander import (
    apply_use_transform,
    compose_use_transform,
    instantiate_use_target,
)
from svg2ooxml.services import configure_services

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"


def _build_parse_result(svg_root: etree._Element) -> ParseResult:
    return ParseResult.success_with(
        svg_root,
        sum(1 for _ in svg_root.iter()),
        namespace_count=1,
        namespaces={"svg": SVG_NS},
        masks={},
        symbols={},
        filters={},
        markers={},
        width_px=100.0,
        height_px=100.0,
        services=configure_services(),
    )


def _expand_use_clone(svg_markup: str) -> etree._Element:
    svg_root = etree.fromstring(svg_markup)
    converter = IRConverter(services=configure_services())
    converter._prepare_context(_build_parse_result(svg_root))

    use_element = svg_root.find(f"{{{SVG_NS}}}use")
    assert use_element is not None

    href = use_element.get(f"{{{XLINK_NS}}}href") or use_element.get("href")
    assert href is not None
    target_id = converter._normalize_href_reference(href)
    assert target_id is not None

    targets = svg_root.xpath(f".//*[@id='{target_id}']")
    assert targets
    target = targets[0]

    clones = instantiate_use_target(converter, target, use_element)
    combined = compose_use_transform(converter, use_element, target, tolerance=1e-6)
    apply_use_transform(converter, clones, combined, tolerance=1e-6)
    assert len(clones) == 1
    return clones[0]


def test_apply_use_transform_does_not_double_apply_target_transform() -> None:
    svg = """
        <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
            <defs>
                <rect id="r" width="2" height="1" transform="translate(5,0)" />
            </defs>
            <use xlink:href="#r" />
        </svg>
    """

    clone = _expand_use_clone(svg)
    matrix = parse_transform_list(clone.get("transform"))

    assert clone.tag.endswith("rect")
    assert matrix.e == 5.0
    assert matrix.f == 0.0


def test_apply_use_transform_preserves_group_transform_with_clip_path() -> None:
    svg = """
        <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
            <defs>
                <clipPath id="c">
                    <rect x="0" y="0" width="5" height="5" />
                </clipPath>
                <g id="g" clip-path="url(#c)">
                    <rect x="0" y="0" width="5" height="5" />
                </g>
            </defs>
            <use xlink:href="#g" transform="translate(10,0)" />
        </svg>
    """

    clone = _expand_use_clone(svg)
    matrix = parse_transform_list(clone.get("transform"))

    assert clone.tag.endswith("g")
    assert clone.get("clip-path") == "url(#c)"
    assert matrix.e == 10.0
    assert matrix.f == 0.0
    assert len(clone) == 1
    assert clone[0].tag.endswith("rect")
    assert clone[0].get("transform") is None


def test_compose_use_transform_keeps_viewbox_offsets_outside_scaling() -> None:
    svg = """
        <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
            <defs>
                <symbol id="icon" viewBox="0 0 10 10">
                    <rect width="10" height="10" />
                </symbol>
            </defs>
            <use xlink:href="#icon" x="50" y="60" width="20" height="40" />
        </svg>
    """

    clone = _expand_use_clone(svg)
    matrix = parse_transform_list(clone.get("transform"))

    assert clone.tag.endswith("g")
    assert matrix.a == 2.0
    assert matrix.d == 2.0
    assert matrix.e == 50.0
    assert matrix.f == 70.0
