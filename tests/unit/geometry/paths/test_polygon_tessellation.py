"""Regression harness for polygon tessellation."""

from __future__ import annotations

import pytest
import json
from pathlib import Path

from lxml import etree

from svg2ooxml.core.parser import ParseResult
from svg2ooxml.common.geometry.paths import compute_segments_bbox
from svg2ooxml.core.ir import IRScene
from svg2ooxml.ir.entrypoints import convert_parser_output
from svg2ooxml.services.setup import configure_services

# TODO(ADR-geometry-ir): Replace with svg2pptx baseline comparison once tessellation data is ported.


def _build_parse_result(svg_markup: str) -> ParseResult:
    svg_root = etree.fromstring(svg_markup)
    services = configure_services()
    element_count = sum(1 for _ in svg_root.iter())
    namespaces = {"svg": "http://www.w3.org/2000/svg"}
    return ParseResult.success_with(
        svg_root,
        element_count,
        namespace_count=len(namespaces),
        namespaces=namespaces,
        masks={},
        symbols={},
        filters={},
        markers={},
        width_px=200.0,
        height_px=200.0,
        services=services,
    )


def test_polygon_path_segments_match_bounding_box() -> None:
    svg = (
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "<polygon points='10,20 60,25 55,70 12,68' fill='#abcdef'/>"
        "</svg>"
    )
    parse_result = _build_parse_result(svg)
    scene = convert_parser_output(parse_result)

    assert isinstance(scene, IRScene)
    assert scene.elements, "expected at least one element"
    element = scene.elements[0]
    if hasattr(element, "segments") and element.segments:
        segments = element.segments
    elif hasattr(element, "points"):
        from svg2ooxml.common.geometry.paths.drawing import to_line_segments

        segments = to_line_segments(element.points)
    else:
        pytest.fail("Expected polygon-like element to provide geometry segments")

    baseline_path = Path(__file__).resolve().parents[3] / "fixtures" / "geometry" / "polygon_simple.json"
    baseline = json.loads(baseline_path.read_text())

    assert len(segments) == len(baseline["segments"])
    for segment, expected in zip(segments, baseline["segments"]):
        assert segment.start.x == pytest.approx(expected["start"][0])
        assert segment.start.y == pytest.approx(expected["start"][1])
        assert segment.end.x == pytest.approx(expected["end"][0])
        assert segment.end.y == pytest.approx(expected["end"][1])

    bbox = compute_segments_bbox(segments)
    exp_bbox = baseline["bbox"]
    assert bbox.x == pytest.approx(exp_bbox[0])
    assert bbox.y == pytest.approx(exp_bbox[1])
    assert bbox.width == pytest.approx(exp_bbox[2])
    assert bbox.height == pytest.approx(exp_bbox[3])
