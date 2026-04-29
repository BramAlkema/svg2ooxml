"""Unit tests for marker transform composition helpers."""

from __future__ import annotations

import pytest
from lxml import etree

from svg2ooxml.core.traversal.marker_geometry import marker_segments_for_element
from svg2ooxml.core.traversal.markers import (
    apply_local_transform,
    build_marker_transform,
    parse_marker_definition,
)
from svg2ooxml.ir.geometry import Point


def _build_marker(markup: str):
    svg = etree.fromstring(
        "<svg xmlns='http://www.w3.org/2000/svg'>"
        f"{markup}"
        "</svg>"
    )
    return svg[0]


def test_build_marker_transform_maps_reference_point_to_anchor_with_viewbox_and_stroke_width() -> None:
    marker = _build_marker(
        "<marker id='m' markerWidth='4' markerHeight='6' markerUnits='strokeWidth' "
        "refX='1' refY='2' orient='90' viewBox='0 0 2 3'>"
        "  <path d='M0,0 L2,0 L2,3 z'/>"
        "</marker>"
    )

    definition = parse_marker_definition(marker)
    transform = build_marker_transform(
        definition=definition,
        anchor=Point(30.0, 20.0),
        angle=0.0,
        stroke_width=5.0,
        position="end",
    )

    assert transform.clip_rect == (0.0, 0.0, 20.0, 30.0)
    ref_x, ref_y = transform.matrix.transform_xy(1.0, 2.0)
    assert ref_x == pytest.approx(30.0)
    assert ref_y == pytest.approx(20.0)

    x0, y0 = transform.matrix.transform_xy(0.0, 0.0)
    x1, y1 = transform.matrix.transform_xy(2.0, 0.0)
    x2, y2 = transform.matrix.transform_xy(2.0, 3.0)
    assert x0 == pytest.approx(50.0)
    assert y0 == pytest.approx(10.0)
    assert x1 == pytest.approx(50.0)
    assert y1 == pytest.approx(30.0)
    assert x2 == pytest.approx(20.0)
    assert y2 == pytest.approx(30.0)


def test_apply_local_transform_uses_marker_space_before_marker_placement() -> None:
    marker = _build_marker(
        "<marker id='m' markerWidth='4' markerHeight='4' markerUnits='userSpaceOnUse' "
        "refX='0' refY='0' orient='0'>"
        "  <path d='M0,0 L1,0'/>"
        "</marker>"
    )

    definition = parse_marker_definition(marker)
    placement = build_marker_transform(
        definition=definition,
        anchor=Point(30.0, 20.0),
        angle=0.0,
        stroke_width=1.0,
        position="end",
    ).matrix

    combined = apply_local_transform(placement, "translate(3,4)")

    start_x, start_y = combined.transform_xy(0.0, 0.0)
    end_x, end_y = combined.transform_xy(1.0, 0.0)
    assert start_x == pytest.approx(33.0)
    assert start_y == pytest.approx(24.0)
    assert end_x == pytest.approx(34.0)
    assert end_y == pytest.approx(24.0)


def test_marker_segments_parse_compact_signed_polyline_points() -> None:
    element = etree.fromstring("<polyline points='0,0 10-5 20,0'/>")

    segments = marker_segments_for_element(element, "polyline")

    assert len(segments) == 2
    assert segments[0].start == Point(0.0, 0.0)
    assert segments[0].end == Point(10.0, -5.0)
    assert segments[1].end == Point(20.0, 0.0)
