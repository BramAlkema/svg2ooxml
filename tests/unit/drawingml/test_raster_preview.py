"""Raster preview SVG helper tests."""

from __future__ import annotations

import math

from lxml import etree

from svg2ooxml.drawingml.raster_preview import RasterPreviewBuilder


def test_preview_viewbox_sanitizes_non_finite_bounds() -> None:
    builder = RasterPreviewBuilder()

    assert (
        builder.preview_viewbox(
            bounds={
                "x": math.inf,
                "y": math.nan,
                "width": "bad",
                "height": -2,
            },
            width_px=20,
            height_px=10,
            preserve_user_space=True,
        )
        == "0 0 20 10"
    )


def test_preview_markup_sanitizes_direct_dimensions() -> None:
    builder = RasterPreviewBuilder()
    filter_clone = etree.Element("{http://www.w3.org/2000/svg}filter", id="blur")

    markup = builder.build_preview_svg_markup(
        filter_clone=filter_clone,
        preview_filter_id="blur",
        width_px=math.inf,
        height_px="bad",
        context=None,
        resolved_bounds=None,
    )

    root = etree.fromstring(markup)
    assert root.get("width") == "1"
    assert root.get("height") == "1"
    assert root.get("viewBox") == "0 0 1 1"


def test_localize_source_subtree_ignores_non_finite_offsets() -> None:
    builder = RasterPreviewBuilder()
    node = etree.Element("{http://www.w3.org/2000/svg}rect")

    result = builder.localize_source_subtree(
        node,
        {"x": math.inf, "y": 1.0},
    )

    assert result is node
    assert node.get("transform") is None


def test_user_space_reference_detection_handles_quoted_url_refs() -> None:
    builder = RasterPreviewBuilder()
    svg = etree.fromstring("""
        <svg xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="grad" gradientUnits="userSpaceOnUse"/>
          </defs>
          <rect style="fill:url('#grad')"/>
        </svg>
        """)
    rect = svg.xpath(".//*[local-name()='rect']")[0]

    assert builder.requires_original_user_space(rect, svg)


def test_background_subtree_includes_ancestor_previous_siblings_until_background_reset() -> None:
    builder = RasterPreviewBuilder()
    svg = etree.fromstring("""
        <svg xmlns="http://www.w3.org/2000/svg">
          <g id="outer">
            <g id="previous-test">
              <rect id="outside" x="0" y="0" width="10" height="10"/>
            </g>
            <g id="test" enable-background="new" transform="translate(100,0)">
              <rect id="rect-bg" x="25" y="25" width="100" height="100"/>
              <g id="opacity-parent" opacity=".5">
                <circle id="circle-bg" cx="125" cy="75" r="45"/>
                <polygon id="target" points="160,25 160,125 240,75"
                         filter="url(#shift)"/>
              </g>
            </g>
          </g>
        </svg>
        """)
    ns = {"svg": "http://www.w3.org/2000/svg"}
    target = svg.xpath(".//svg:polygon[@id='target']", namespaces=ns)[0]

    subtree = builder.build_background_subtree(
        source_element=target,
        source_root=svg,
        svg_ns="http://www.w3.org/2000/svg",
    )

    assert subtree is not None
    assert subtree.xpath(".//*[@id='rect-bg']")
    assert subtree.xpath(".//*[@id='circle-bg']")
    assert not subtree.xpath(".//*[@id='target']")
    assert not subtree.xpath(".//*[@id='outside']")
    opacity_parent = subtree.xpath(".//*[@id='opacity-parent']")[0]
    assert opacity_parent.get("opacity") is None
