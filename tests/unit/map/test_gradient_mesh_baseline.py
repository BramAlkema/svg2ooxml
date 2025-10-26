"""Baseline comparison for mesh gradient metadata."""

from __future__ import annotations

import json
from pathlib import Path

from lxml import etree

from svg2ooxml.map.ir_converter import convert_parser_output
from svg2ooxml.policy.constants import FALLBACK_EMF
from svg2ooxml.parser.result import ParseResult
from svg2ooxml.services.setup import configure_services


def _build_parse_result(svg_markup: str) -> ParseResult:
    svg_root = etree.fromstring(svg_markup)
    services = configure_services()
    gradients = {
        gradient.get("id"): gradient
        for gradient in svg_root.findall(".//{http://www.w3.org/2000/svg}meshgradient")
        if gradient.get("id")
    }
    if gradients:
        services.register("gradients", gradients)
    return ParseResult.success_with(
        svg_root,
        element_count=sum(1 for _ in svg_root.iter()),
        namespace_count=1,
        namespaces={"svg": "http://www.w3.org/2000/svg"},
        masks={},
        symbols={},
        filters={},
        markers={},
        width_px=120.0,
        height_px=120.0,
        services=services,
    )


def test_mesh_gradient_metadata_matches_baseline() -> None:
    svg = (
        "<svg width='60' height='60' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <meshgradient id='meshGrad'>"
        "    <meshrow>"
        "      <meshpatch><stop offset='0' stop-color='#ff0000'/></meshpatch>"
        "      <meshpatch><stop offset='1' stop-color='#0000ff'/></meshpatch>"
        "    </meshrow>"
        "  </meshgradient>"
        "</defs>"
        "<rect width='30' height='15' fill='url(#meshGrad)'/>"
        "</svg>"
    )
    parse_result = _build_parse_result(svg)
    scene = convert_parser_output(parse_result)

    rect = scene.elements[0]
    baseline_path = Path(__file__).resolve().parents[2] / "fixtures" / "paint" / "mesh_gradient_metadata.json"
    baseline = json.loads(baseline_path.read_text())

    analysis = rect.metadata.get("paint_analysis", {}).get("fill", {}).get("gradient", {})
    assert analysis.get("type") == "mesh"
    assert analysis.get("mesh_rows") == baseline["mesh_rows"]
    assert analysis.get("mesh_columns") == baseline["mesh_columns"]
    assert analysis.get("patch_count") == baseline["patch_count"]
    assert analysis.get("stop_count") == baseline["stop_count"]
    assert sorted(analysis.get("colors_used", [])) == sorted(baseline["colors_used"])

    paint_policy = rect.metadata.get("policy", {}).get("paint", {}).get("fill", {})
    for key, value in baseline["paint_policy"].items():
        if key == "suggest_fallback":
            continue
        assert paint_policy.get(key) == value
    assert paint_policy.get("suggest_fallback") == FALLBACK_EMF

    geometry_policy = rect.metadata.get("policy", {}).get("geometry", {})
    for key, value in baseline["geometry_policy"].items():
        if key == "suggest_fallback":
            continue
        assert geometry_policy.get(key) == value
    assert geometry_policy.get("suggest_fallback") == FALLBACK_EMF
