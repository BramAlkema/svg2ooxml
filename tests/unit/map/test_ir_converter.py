"""Tests for the IR converter pipeline."""

from __future__ import annotations

import pytest
from lxml import etree

from svg2ooxml.core.ir import IRConverter, IRScene
from svg2ooxml.ir.entrypoints import convert_parser_output
from svg2ooxml.ir.scene import Group, Image, Path, Rectangle
from svg2ooxml.ir.text import TextFrame
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect
from svg2ooxml.ir.shapes import Circle, Ellipse, Rectangle, Line, Polyline, Polygon
from svg2ooxml.ir.paint import GradientPaintRef, LinearGradientPaint, PatternPaint, SolidPaint, Stroke
from svg2ooxml.core.parser import ParseResult
from svg2ooxml.policy import PolicyContext, PolicyEngine
from svg2ooxml.policy.constants import FALLBACK_BITMAP, FALLBACK_EMF
from svg2ooxml.services import configure_services


def _build_parse_result(svg_markup: str) -> ParseResult:
    svg_root = etree.fromstring(svg_markup)
    services = configure_services()
    element_count = sum(1 for _ in svg_root.iter())
    namespaces = {"svg": "http://www.w3.org/2000/svg"}
    symbols: dict[str, etree._Element] = {}
    for node in svg_root.iter():
        node_id = node.get("id")
        if node_id and node.tag.endswith("symbol"):
            symbols[node_id] = node
    markers: dict[str, etree._Element] = {}
    for marker in svg_root.findall(".//{http://www.w3.org/2000/svg}marker"):
        marker_id = marker.get("id")
        if marker_id:
            markers[marker_id] = marker
    gradient_defs: dict[str, etree._Element] = {}
    gradient_paths = [
        ".//{http://www.w3.org/2000/svg}linearGradient",
        ".//{http://www.w3.org/2000/svg}radialGradient",
        ".//{http://www.w3.org/2000/svg}meshgradient",
    ]
    for path in gradient_paths:
        for gradient in svg_root.findall(path):
            gradient_id = gradient.get("id")
            if gradient_id:
                gradient_defs[gradient_id] = gradient
    if gradient_defs:
        services.register("gradients", gradient_defs)
    pattern_defs: dict[str, etree._Element] = {}
    for pattern in svg_root.findall(".//{http://www.w3.org/2000/svg}pattern"):
        pattern_id = pattern.get("id")
        if pattern_id:
            pattern_defs[pattern_id] = pattern
    if pattern_defs:
        services.register("patterns", pattern_defs)
    parse_result = ParseResult.success_with(
        svg_root,
        element_count,
        namespace_count=len(namespaces),
        namespaces=namespaces,
        masks={},
        symbols=symbols,
        filters={},
        markers=markers,
        width_px=200.0,
        height_px=200.0,
        services=services,
    )
    return parse_result


def _register_filter(parse_result: ParseResult, filter_markup: str) -> None:
    filters = parse_result.filters or {}
    element = etree.fromstring(filter_markup)
    filter_id = element.get("id", "filter")
    filters[filter_id] = element
    parse_result.filters = filters  # type: ignore[assignment]


def test_legacy_core_module_exposes_ir_converter() -> None:
    from svg2ooxml.map.converter.core import IRConverter as LegacyIRConverter

    assert LegacyIRConverter is IRConverter


def test_convert_rect_produces_rectangle() -> None:
    parse_result = _build_parse_result(
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "<rect x='10' y='20' width='30' height='40' fill='#ff0000'/>"
        "</svg>"
    )

    scene = convert_parser_output(parse_result)

    assert isinstance(scene, IRScene)
    assert len(scene.elements) == 1
    rect = scene.elements[0]
    assert isinstance(rect, Rectangle)
    assert rect.bounds.x == 10
    assert rect.bounds.y == 20
    assert rect.bounds.width == 30
    assert rect.bounds.height == 40
    assert rect.fill is not None and rect.fill.rgb == "FF0000"


def test_convert_rect_with_corner_radius_preserves_native_shape() -> None:
    parse_result = _build_parse_result(
        "<svg width='100' height='100' xmlns='http://www.w3.org/2000/svg'>"
        "<rect x='5' y='6' width='20' height='30' rx='4' ry='4' fill='#123456'/>"
        "</svg>"
    )

    scene = convert_parser_output(parse_result)

    rect = scene.elements[0]
    assert isinstance(rect, Rectangle)
    assert rect.corner_radius == pytest.approx(4.0)
    assert rect.bounds.x == pytest.approx(5.0)
    assert rect.bounds.y == pytest.approx(6.0)


def test_convert_line_produces_native_line() -> None:
    parse_result = _build_parse_result(
        "<svg width='100' height='100' xmlns='http://www.w3.org/2000/svg'>"
        "<line x1='5' y1='6' x2='25' y2='26' stroke='#123456' stroke-width='2'/>"
        "</svg>"
    )

    scene = convert_parser_output(parse_result)

    shape = scene.elements[0]
    assert isinstance(shape, Line)
    assert shape.start.x == pytest.approx(5.0)
    assert shape.end.y == pytest.approx(26.0)
    assert shape.stroke is not None and shape.stroke.paint.rgb == "123456"


def test_convert_polyline_produces_native_polyline() -> None:
    parse_result = _build_parse_result(
        "<svg width='100' height='100' xmlns='http://www.w3.org/2000/svg'>"
        "<polyline points='0,0 10,10 20,0' stroke='#00AAFF' stroke-width='1.5' fill='none'/>"
        "</svg>"
    )

    scene = convert_parser_output(parse_result)

    shape = scene.elements[0]
    assert isinstance(shape, Polyline)
    assert len(shape.points) == 3
    assert shape.points[1].x == pytest.approx(10.0)
    assert shape.stroke is not None and shape.stroke.paint.rgb == "00AAFF"


def test_convert_polygon_produces_native_polygon() -> None:
    parse_result = _build_parse_result(
        "<svg width='100' height='100' xmlns='http://www.w3.org/2000/svg'>"
        "<polygon points='10,10 30,10 20,25' fill='#AA5500' stroke='#002244'/>"
        "</svg>"
    )

    scene = convert_parser_output(parse_result)

    shape = scene.elements[0]
    assert isinstance(shape, Polygon)
    assert len(shape.points) == 3
    assert shape.points[0].x == pytest.approx(10.0)
    assert shape.fill is not None and shape.fill.rgb == "AA5500"


def test_convert_rotated_rounded_rect_generates_bezier_path() -> None:
    parse_result = _build_parse_result(
        "<svg width='120' height='120' xmlns='http://www.w3.org/2000/svg'>"
        "<rect x='10' y='15' width='40' height='25' rx='5' transform='rotate(30 30 27.5)'/>"
        "</svg>"
    )

    scene = convert_parser_output(parse_result)

    shape = scene.elements[0]
    assert isinstance(shape, Path)
    assert any(isinstance(segment, BezierSegment) for segment in shape.segments)


def test_use_symbol_expands_children() -> None:
    parse_result = _build_parse_result(
        "<svg width='120' height='120' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <symbol id='icon'>"
        "    <rect width='10' height='20'/>"
        "  </symbol>"
        "</defs>"
        "<use id='inst1' x='5' y='7' href='#icon' fill='#010203'/>"
        "</svg>"
    )

    scene = convert_parser_output(parse_result)

    assert len(scene.elements) == 1
    group = scene.elements[0]
    assert isinstance(group, Group)
    assert group.clip is None
    assert group.transform is None
    assert len(group.children) == 1
    rect = group.children[0]
    assert isinstance(rect, Rectangle)
    assert rect.bounds.x == pytest.approx(5.0)
    assert rect.bounds.y == pytest.approx(7.0)
    assert rect.bounds.width == pytest.approx(10.0)
    assert rect.bounds.height == pytest.approx(20.0)
    assert rect.fill is not None and rect.fill.rgb == "010203"
    element_ids = set(group.metadata.get("element_ids", []))
    assert "inst1" in element_ids


def test_foreign_object_with_nested_svg_produces_group() -> None:
    parse_result = _build_parse_result(
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "  <foreignObject x='10' y='15' width='40' height='30'>"
        "    <svg xmlns='http://www.w3.org/2000/svg'>"
        "      <rect width='10' height='12' fill='#00AAFF'/>"
        "    </svg>"
        "  </foreignObject>"
        "</svg>"
    )

    scene = convert_parser_output(parse_result)

    assert len(scene.elements) == 1
    group = scene.elements[0]
    assert isinstance(group, Group)
    assert group.clip is not None
    assert group.clip.clip_id.startswith("foreignObject:")
    assert any(isinstance(child, Rectangle) for child in group.children)
    metadata = group.metadata.get("foreign_object", {})
    assert metadata.get("payload_type") == "nested_svg"


def test_foreign_object_image_emits_image_ir() -> None:
    parse_result = _build_parse_result(
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "  <foreignObject x='0' y='0' width='50' height='60'>"
        "    <img src='https://example.com/foo.png'/>"
        "  </foreignObject>"
        "</svg>"
    )

    scene = convert_parser_output(parse_result)

    assert len(scene.elements) == 1
    image = scene.elements[0]
    assert isinstance(image, Image)
    assert image.href == "https://example.com/foo.png"
    assert image.clip is not None and image.clip.clip_id.startswith("foreignObject:")
    metadata = image.metadata.get("foreign_object", {})
    assert metadata.get("payload_type") == "image"


def test_foreign_object_xhtml_creates_text_frame() -> None:
    parse_result = _build_parse_result(
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "  <foreignObject x='5' y='10' width='80' height='40'>"
        "    <div xmlns='http://www.w3.org/1999/xhtml'>Hello <span>World</span></div>"
        "  </foreignObject>"
        "</svg>"
    )

    scene = convert_parser_output(parse_result)

    assert len(scene.elements) == 1
    frame = scene.elements[0]
    assert isinstance(frame, TextFrame)
    assert frame.text_content == "Hello World"
    metadata = frame.metadata.get("foreign_object", {})
    assert metadata.get("payload_type") == "xhtml"


def test_use_element_reuses_existing_geometry() -> None:
    parse_result = _build_parse_result(
        "<svg width='160' height='160' xmlns='http://www.w3.org/2000/svg'>"
        "<rect id='baseRect' width='8' height='9' fill='#FF00FF'/>"
        "<use id='copyRect' href='#baseRect' x='25' y='35'/>"
        "</svg>"
    )

    scene = convert_parser_output(parse_result)

    assert len(scene.elements) == 2
    first_rect = scene.elements[0]
    second_rect = scene.elements[1]
    assert isinstance(first_rect, Rectangle)
    assert isinstance(second_rect, Rectangle)
    assert first_rect.bounds.x == pytest.approx(0.0)
    assert first_rect.bounds.y == pytest.approx(0.0)
    assert second_rect.bounds.x == pytest.approx(25.0)
    assert second_rect.bounds.y == pytest.approx(35.0)
    assert second_rect.fill is not None and second_rect.fill.rgb == "FF00FF"
    element_ids = set(second_rect.metadata.get("element_ids", []))
    assert "copyRect" in element_ids


def test_use_symbol_applies_viewbox_scaling() -> None:
    parse_result = _build_parse_result(
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <symbol id='vbSymbol' viewBox='0 0 10 5'>"
        "    <rect width='10' height='5'/>"
        "  </symbol>"
        "</defs>"
        "<use id='scaled' href='#vbSymbol' width='20' height='40' preserveAspectRatio='none'/>"
        "</svg>"
    )

    scene = convert_parser_output(parse_result)

    assert len(scene.elements) == 1
    group = scene.elements[0]
    assert isinstance(group, Group)
    assert len(group.children) == 1
    rect = group.children[0]
    assert isinstance(rect, Rectangle)
    assert rect.bounds.width == pytest.approx(20.0)
    assert rect.bounds.height == pytest.approx(40.0)


def test_use_symbol_viewbox_meet_preserves_aspect_ratio() -> None:
    parse_result = _build_parse_result(
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <symbol id='vbSymbol' viewBox='0 0 10 5'>"
        "    <rect width='10' height='5'/>"
        "  </symbol>"
        "</defs>"
        "<use id='scaled' href='#vbSymbol' width='20' height='40'/>"
        "</svg>"
    )

    scene = convert_parser_output(parse_result)

    group = scene.elements[0]
    rect = group.children[0]
    assert rect.bounds.width == pytest.approx(20.0)
    assert rect.bounds.height == pytest.approx(10.0)


def test_filter_metadata_carries_fallback_assets_into_policy() -> None:
    svg = (
        "<svg width='120' height='120' xmlns='http://www.w3.org/2000/svg'>"
        "  <defs>"
        "    <filter id='glow'>"
        "      <feFlood flood-color='#AA8844' flood-opacity='0.5' result='flood'/>"
        "      <feMorphology operator='dilate' radius='6' in='flood'/>"
        "    </filter>"
        "  </defs>"
        "  <rect id='shape' x='10' y='10' width='40' height='40' filter='url(#glow)'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)
    _register_filter(
        parse_result,
        "<filter id='glow'>"
        "  <feFlood flood-color='#AA8844' flood-opacity='0.5' result='first'/>"
        "  <feFlood flood-color='#445588' flood-opacity='0.4' result='second'/>"
        "  <feBlend mode='multiply' in='first' in2='second'/>"
        "</filter>",
    )

    scene = convert_parser_output(parse_result)

    assert len(scene.elements) == 1
    rect = scene.elements[0]
    assert isinstance(rect, Rectangle)
    filter_meta = rect.metadata.get("filter_metadata", {})
    assert "glow" in filter_meta
    assets = filter_meta["glow"].get("fallback_assets")
    assert assets and any(asset.get("type") == "emf" for asset in assets)
    media_policy = rect.metadata.get("policy", {}).get("media", {})
    filter_assets = media_policy.get("filter_assets", {})
    assert "glow" in filter_assets


def test_gradient_fill_resolves_to_linear_gradient() -> None:
    svg = (
        "<svg width='100' height='100' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <linearGradient id='gradA' x1='0%' y1='0%' x2='100%' y2='0%'>"
        "    <stop offset='0%' stop-color='#000000'/>"
        "    <stop offset='100%' stop-color='#ffffff' stop-opacity='0.5'/>"
        "  </linearGradient>"
        "</defs>"
        "<rect width='50' height='20' fill='url(#gradA)'/>"
        "</svg>"
    )
    parse_result = _build_parse_result(svg)

    scene = convert_parser_output(parse_result)

    rect = scene.elements[0]
    assert isinstance(rect, Rectangle)
    assert isinstance(rect.fill, LinearGradientPaint)
    assert rect.fill.gradient_id == "gradA"
    assert len(rect.fill.stops) == 2
    assert rect.fill.stops[0].rgb == "000000"
    assert rect.fill.stops[1].opacity == pytest.approx(0.5)
    paint_policy = rect.metadata.get("policy", {}).get("paint", {})
    assert paint_policy.get("fill", {}).get("type") == "gradient"
    assert paint_policy["fill"]["id"] == "gradA"
    assert "suggest_fallback" not in paint_policy["fill"]
    analysis = rect.metadata.get("paint_analysis", {}).get("fill", {}).get("gradient")
    assert analysis is not None
    assert analysis["stop_count"] == 2




def test_mesh_gradient_records_policy_metadata() -> None:
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
    assert isinstance(rect, Rectangle)
    assert isinstance(rect.fill, GradientPaintRef)
    assert rect.fill.gradient_id == 'meshGrad'
    assert rect.fill.gradient_type == 'mesh'
    analysis = rect.metadata.get('paint_analysis', {}).get('fill', {}).get('gradient')
    assert analysis is not None
    assert analysis['type'] == 'mesh'
    assert analysis['patch_count'] == 2
    paint_policy = rect.metadata.get('policy', {}).get('paint', {}).get('fill', {})
    assert paint_policy.get('gradient_kind') == 'mesh'
    assert paint_policy.get('suggest_fallback') == FALLBACK_EMF
    geometry_policy = rect.metadata.get('policy', {}).get('geometry', {})
    assert geometry_policy.get('suggest_fallback') == FALLBACK_EMF
def test_gradient_fill_resolves_without_parser_services() -> None:
    svg = (
        "<svg width='80' height='80' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <linearGradient id='gradB'>"
        "    <stop offset='0%' stop-color='#ff0000'/>"
        "    <stop offset='100%' stop-color='#00ff00'/>"
        "  </linearGradient>"
        "</defs>"
        "<rect width='40' height='10' fill='url(#gradB)'/>"
        "</svg>"
    )
    parse_result = _build_parse_result(svg)
    object.__setattr__(parse_result, "services", None)

    scene = convert_parser_output(parse_result)

    rect = scene.elements[0]
    assert isinstance(rect, Rectangle)
    assert isinstance(rect.fill, LinearGradientPaint)
    assert rect.fill.gradient_id == "gradB"


def test_text_tspan_produces_multiple_runs() -> None:
    svg = (
        "<svg width='80' height='20' xmlns='http://www.w3.org/2000/svg'>"
        "<text x='0' y='10'>"
        "  Base "
        "  <tspan font-weight='bold'>Bold</tspan>"
        "  <tspan fill='#00ff00'>Green</tspan>"
        "</text>"
        "</svg>"
    )
    parse_result = _build_parse_result(svg)

    scene = convert_parser_output(parse_result)

    text = scene.elements[0]
    assert isinstance(text, TextFrame)
    assert any(run.text.strip() == "Base" for run in text.runs)
    assert any(run.bold and run.text.strip() == "Bold" for run in text.runs)
    assert any(run.rgb == "00FF00" and "Green" in run.text for run in text.runs)


def test_textpath_metadata_captured() -> None:
    svg = (
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "<defs><path id='curve' d='M0 0 L 50 0'/></defs>"
        "<text><textPath href='#curve'>Hello</textPath></text>"
        "</svg>"
    )
    parse_result = _build_parse_result(svg)

    scene = convert_parser_output(parse_result)

    assert len(scene.elements) == 1
    text = scene.elements[0]
    assert isinstance(text, TextFrame)
    assert text.metadata.get("text_path_id") == "curve"
    assert "text_path_points" in text.metadata
    assert isinstance(text.metadata["text_path_points"], list)


def test_inline_navigation_attributes_attach_metadata() -> None:
    svg = (
        "<svg width='100' height='60' xmlns='http://www.w3.org/2000/svg'>"
        "  <rect width='20' height='10' fill='#ff00ff' data-slide='3' title='Jump'/>"
        "</svg>"
    )
    parse_result = _build_parse_result(svg)

    scene = convert_parser_output(parse_result)

    rect = scene.elements[0]
    assert isinstance(rect, Rectangle)
    navigation = rect.metadata.get('navigation')
    assert navigation is not None
    assert navigation['kind'] == 'slide'
    assert navigation['slide']['index'] == 3
    assert rect.metadata.get('attributes', {}).get('title') == 'Jump'


def test_group_navigation_attributes_propagate_to_children() -> None:
    svg = (
        "<svg width='120' height='80' xmlns='http://www.w3.org/2000/svg'>"
        "  <g data-custom-show='deckA'>"
        "    <rect id='card' width='30' height='15' fill='#00aaff' />"
        "  </g>"
        "</svg>"
    )
    parse_result = _build_parse_result(svg)

    scene = convert_parser_output(parse_result)

    group = scene.elements[0]
    assert isinstance(group, Group)
    nav = group.metadata.get('navigation')
    assert nav is not None
    assert nav['kind'] == 'custom_show'
    assert nav['custom_show']['name'] == 'deckA'

    child = group.children[0]
    assert isinstance(child, Rectangle)
    child_nav = child.metadata.get('navigation')
    assert child_nav is not None
    assert child_nav['custom_show']['name'] == 'deckA'


def test_filter_reference_marks_bitmap_fallback() -> None:
    svg = (
        "<svg width='40' height='40' xmlns='http://www.w3.org/2000/svg'>"
        "  <defs>"
        "    <filter id='glow'><feGaussianBlur stdDeviation='5'/></filter>"
        "  </defs>"
        "  <rect id='shape' width='20' height='10' filter='url(#glow)'/>"
        "</svg>"
    )
    parse_result = _build_parse_result(svg)

    scene = convert_parser_output(parse_result)

    rect = scene.elements[0]
    assert isinstance(rect, Rectangle)
    filters_meta = rect.metadata.get('filters')
    assert isinstance(filters_meta, list)
    entry = next(iter(filters_meta))
    assert entry['id'] == 'glow'
    assert entry['strategy'] in {'native', 'raster', 'auto', 'resvg'}
    # Entry may omit fallback when a native strategy is selected
    if entry.get('fallback'):
        assert entry['fallback'] in {'bitmap', 'emf', 'vector'}
    geometry_policy = rect.metadata.get('policy', {}).get('geometry', {})
    if 'suggest_fallback' in geometry_policy:
        assert geometry_policy['suggest_fallback'] in {FALLBACK_BITMAP, 'emf', 'vector'}
    assert rect.effects, "expected filter to add custom effects"
    filters_policy = rect.metadata.get('policy', {}).get('effects', {}).get('filters', [])
    assert any(item.get('id') == 'glow' for item in filters_policy)


def test_displacement_map_filter_metadata() -> None:
    svg = (
        "<svg width='40' height='40' xmlns='http://www.w3.org/2000/svg'>"
        "  <defs>"
        "    <filter id='disp'><feDisplacementMap in2='map' scale='10'/></filter>"
        "  </defs>"
        "  <rect width='20' height='10' filter='url(#disp)'/>"
        "</svg>"
    )
    parse_result = _build_parse_result(svg)

    scene = convert_parser_output(parse_result)

    rect = scene.elements[0]
    assert isinstance(rect, Rectangle)
    filters_meta = rect.metadata.get('filters', [])
    assert any(entry.get('id') == 'disp' for entry in filters_meta)
    filter_meta = rect.metadata.get('filter_metadata', {}).get('disp', {})
    assert filter_meta is not None
    geometry_policy = rect.metadata.get('policy', {}).get('geometry', {})
    if 'suggest_fallback' in geometry_policy:
        assert geometry_policy['suggest_fallback'] in {FALLBACK_BITMAP, FALLBACK_EMF, 'vector'}
    filters_policy = rect.metadata.get('policy', {}).get('effects', {}).get('filters', [])
    assert any(item.get('id') == 'disp' for item in filters_policy)


def test_path_with_marker_metadata() -> None:
    svg = (
        "<svg width='50' height='50' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <marker id='arrow' markerWidth='3' markerHeight='3' orient='auto'>"
        "    <path d='M0,0 L3,1.5 L0,3 z'/>"
        "  </marker>"
        "</defs>"
        "<path d='M0 0 L10 0' stroke='#000000' marker-end='url(#arrow)' fill='none'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)
    scene = convert_parser_output(parse_result)

    paths = [element for element in scene.elements if isinstance(element, Path)]
    assert paths, "expected at least one path element in scene"
    markers = paths[0].metadata.get("markers", {}) if isinstance(paths[0].metadata, dict) else {}
    assert markers.get("end") == "arrow"


def test_pattern_fill_records_policy_metadata() -> None:
    svg = (
        "<svg width='50' height='50' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <pattern id='grid' width='4' height='4' patternUnits='userSpaceOnUse'>"
        "    <rect x='0' y='0' width='4' height='1' fill='#333'/>"
        "    <rect x='0' y='0' width='1' height='4' fill='#666'/>"
        "  </pattern>"
        "</defs>"
        "<rect width='20' height='20' fill='url(#grid)'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)
    scene = convert_parser_output(parse_result)

    rect = scene.elements[0]
    assert isinstance(rect, Rectangle)
    paint_policy = rect.metadata.get("policy", {}).get("paint", {})
    assert paint_policy.get("fill", {}).get("type") == "pattern"
    assert paint_policy["fill"]["id"] == "grid"
    analysis = rect.metadata.get("paint_analysis", {}).get("fill", {}).get("pattern")
    assert analysis is not None
    assert analysis["id"] == "grid"


def test_polygon_respects_geometry_policy(monkeypatch):
    svg = (
        "<svg width='40' height='40' xmlns='http://www.w3.org/2000/svg'>"
        "<polygon points='0,0 20,0 20,20 0,20' fill='#00FF00'/>"
        "</svg>"
    )
    parse_result = _build_parse_result(svg)
    engine = PolicyEngine()
    parse_result.policy_engine = engine
    parse_result.policy_context = PolicyContext(
        selections={"geometry": {"max_segments": 1, "simplify_paths": False}}
    )
    calls: dict[str, object] = {}

    def fake_convert_path_to_emf(
        self,
        *,
        element,
        style,
        segments,
        coord_space,
        clip_ref,
        mask_ref,
        mask_instance,
        metadata,
    ):
        calls["called"] = True
        metadata = dict(metadata)
        metadata.setdefault("policy", {}).setdefault("geometry", {})["render_mode"] = "emf"
        return Image(
            origin=Point(0.0, 0.0),
            size=Rect(0.0, 0.0, 1.0, 1.0),
            data=b"emf",
            format="emf",
            clip=clip_ref,
            mask=mask_ref,
            opacity=style.opacity,
            metadata=metadata,
        )

    monkeypatch.setattr(IRConverter, "_convert_path_to_emf", fake_convert_path_to_emf)

    scene = convert_parser_output(parse_result)

    assert calls.get("called") is True
    assert any(isinstance(elem, Image) and elem.format == "emf" for elem in scene.elements)


def test_clip_ref_generates_custom_geometry() -> None:
    svg = (
        "<svg width='50' height='50' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <clipPath id='clipRect'>"
        "    <rect x='5' y='5' width='20' height='10'/>"
        "  </clipPath>"
        "</defs>"
        "<rect x='0' y='0' width='30' height='20' clip-path='url(#clipRect)' fill='#abc123'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)

    scene = convert_parser_output(parse_result)

    paths = [element for element in scene.elements if isinstance(element, Path)]
    assert paths, "expected at least one path element due to clipping"
    clipped_path = next(path for path in paths if path.clip is not None)
    clip_ref = clipped_path.clip
    assert clip_ref is not None
    assert clip_ref.custom_geometry_xml is not None
    assert clip_ref.custom_geometry_bounds is not None
    assert clip_ref.custom_geometry_bounds.width > 0
    assert clip_ref.custom_geometry_bounds.height > 0
    assert clip_ref.custom_geometry_size is not None
    assert 'prst="rect"' in clip_ref.custom_geometry_xml


def test_clip_ref_circle_uses_preset_geometry() -> None:
    svg = (
        "<svg width='60' height='60' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <clipPath id='clipCircle'>"
        "    <circle cx='20' cy='20' r='10'/>"
        "  </clipPath>"
        "</defs>"
        "<rect x='0' y='0' width='40' height='40' clip-path='url(#clipCircle)' fill='#00ff00'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)

    scene = convert_parser_output(parse_result)

    paths = [element for element in scene.elements if isinstance(element, Path)]
    assert paths, "expected a clipped path element"
    clipped_path = next(path for path in paths if path.clip is not None)
    clip_ref = clipped_path.clip
    assert clip_ref is not None
    assert clip_ref.custom_geometry_xml is not None
    assert 'prst="ellipse"' in clip_ref.custom_geometry_xml


def test_clip_ref_rotated_rect_falls_back_to_custom_geometry() -> None:
    svg = (
        "<svg width='60' height='60' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <clipPath id='rotatedRect'>"
        "    <rect x='10' y='10' width='20' height='10' transform='rotate(30 20 15)'/>"
        "  </clipPath>"
        "</defs>"
        "<rect x='5' y='5' width='40' height='30' clip-path='url(#rotatedRect)' fill='#123456'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)

    scene = convert_parser_output(parse_result)

    paths = [element for element in scene.elements if isinstance(element, Path)]
    assert paths, "expected a clipped path element"
    clip_ref = next(path.clip for path in paths if path.clip is not None)
    assert clip_ref is not None
    assert clip_ref.custom_geometry_xml is not None
    assert "<a:custGeom>" in clip_ref.custom_geometry_xml


def test_clip_ref_round_rect_uses_roundrect_preset() -> None:
    svg = (
        "<svg width='80' height='80' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <clipPath id='roundRect'>"
        "    <rect x='10' y='10' width='40' height='30' rx='6' ry='6'/>"
        "  </clipPath>"
        "</defs>"
        "<rect x='0' y='0' width='70' height='60' clip-path='url(#roundRect)' fill='#998877'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)

    scene = convert_parser_output(parse_result)

    clip_ref = next(path.clip for path in scene.elements if isinstance(path, Path) and path.clip is not None)
    assert clip_ref.custom_geometry_xml is not None
    assert 'prst="roundRect"' in clip_ref.custom_geometry_xml
    assert 'name="rad"' in clip_ref.custom_geometry_xml


def test_clip_ref_mirrored_rect_uses_preset_geometry() -> None:
    svg = (
        "<svg width='80' height='80' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <clipPath id='mirrorRect'>"
        "    <rect x='5' y='5' width='20' height='15' transform='matrix(-1 0 0 1 40 0)'/>"
        "  </clipPath>"
        "</defs>"
        "<rect x='0' y='0' width='60' height='50' clip-path='url(#mirrorRect)' fill='#222222'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)

    scene = convert_parser_output(parse_result)

    clip_ref = next(path.clip for path in scene.elements if isinstance(path, Path) and path.clip is not None)
    assert clip_ref.custom_geometry_xml is not None
    assert 'prst="rect"' in clip_ref.custom_geometry_xml
    assert "<a:custGeom>" not in clip_ref.custom_geometry_xml


def test_clip_ref_mirrored_round_rect_uses_roundrect_preset() -> None:
    svg = (
        "<svg width='90' height='90' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <clipPath id='mirrorRound'>"
        "    <rect x='10' y='15' width='30' height='20' rx='4' ry='4' transform='matrix(-1 0 0 1 60 0)'/>"
        "  </clipPath>"
        "</defs>"
        "<rect x='0' y='0' width='80' height='70' clip-path='url(#mirrorRound)' fill='#abcdef'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)

    scene = convert_parser_output(parse_result)

    clip_ref = next(path.clip for path in scene.elements if isinstance(path, Path) and path.clip is not None)
    assert clip_ref.custom_geometry_xml is not None
    assert 'prst="roundRect"' in clip_ref.custom_geometry_xml
    assert 'name="rad"' in clip_ref.custom_geometry_xml


def test_clip_ref_elliptical_radius_uses_snip_round_preset() -> None:
    svg = (
        "<svg width='80' height='80' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <clipPath id='elliptical'>"
        "    <rect x='8' y='12' width='40' height='30' rx='12' ry='4'/>"
        "  </clipPath>"
        "</defs>"
        "<rect x='0' y='0' width='70' height='60' clip-path='url(#elliptical)' fill='#ddeeff'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)

    scene = convert_parser_output(parse_result)

    clip_ref = next(path.clip for path in scene.elements if isinstance(path, Path) and path.clip is not None)
    xml = clip_ref.custom_geometry_xml
    assert xml is not None
    assert 'prst="snipRoundRect"' in xml
    assert 'name="snip"' in xml
    assert 'name="rad"' in xml


def test_clip_ref_mirrored_elliptical_radius_uses_snip_round_preset() -> None:
    svg = (
        "<svg width='90' height='90' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <clipPath id='mirrorElliptical'>"
        "    <rect x='10' y='15' width='30' height='25' rx='3' ry='10' transform='matrix(-1 0 0 1 60 0)'/>"
        "  </clipPath>"
        "</defs>"
        "<rect x='0' y='0' width='80' height='70' clip-path='url(#mirrorElliptical)' fill='#aabbcc'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)

    scene = convert_parser_output(parse_result)

    clip_ref = next(path.clip for path in scene.elements if isinstance(path, Path) and path.clip is not None)
    xml = clip_ref.custom_geometry_xml
    assert xml is not None
    assert 'prst="snipRoundRect"' in xml
    assert 'name="snip"' in xml
    assert 'name="rad"' in xml

def test_path_markers_expand_scene_with_marker_geometry() -> None:
    svg = (
        "<svg width='50' height='50' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <marker id='arrow' markerWidth='3' markerHeight='3' orient='auto'>"
        "    <path d='M0,0 L3,1.5 L0,3 z' fill='context-stroke'/>"
        "  </marker>"
        "</defs>"
        "<path d='M0 0 L10 0' stroke='#123456' stroke-width='2' marker-start='url(#arrow)' marker-end='url(#arrow)' fill='none'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)
    scene = convert_parser_output(parse_result)

    paths = [element for element in scene.elements if isinstance(element, Path)]
    assert len(paths) == 3, "expected base path plus start/end marker geometries"

    base_path = paths[0]
    assert isinstance(base_path.stroke, Stroke)
    assert isinstance(base_path.stroke.paint, SolidPaint)
    assert base_path.stroke.paint.rgb.upper() == "123456"

    marker_paths = paths[1:]
    assert all(isinstance(marker.metadata, dict) for marker in marker_paths)

    marker_sources = {marker.metadata.get("marker_position") for marker in marker_paths}
    assert marker_sources == {"start", "end"}

    for marker in marker_paths:
        assert marker.metadata.get("source") == "marker"
        assert marker.metadata.get("marker_id") == "arrow"
        assert isinstance(marker.fill, SolidPaint)
        assert marker.fill.rgb.upper() == base_path.stroke.paint.rgb.upper()


def test_marker_group_generates_multiple_shapes() -> None:
    svg = (
        "<svg width='60' height='40' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <marker id='multi' markerWidth='4' markerHeight='4' orient='auto'>"
        "    <g>"
        "      <path d='M0,0 L2,1 L0,2 z' fill='context-stroke'/>"
        "      <path d='M0,2 L2,2 L1,1 z' fill='#ff0000'/>"
        "    </g>"
        "  </marker>"
        "</defs>"
        "<path d='M0 0 L20 0' stroke='#00FF00' stroke-width='2' marker-start='url(#multi)' marker-end='url(#multi)' fill='none'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)
    scene = convert_parser_output(parse_result)

    marker_paths = [
        element
        for element in scene.elements
        if isinstance(element, Path) and element.metadata.get("source") == "marker"
    ]
    assert len(marker_paths) == 4
    positions = {path.metadata.get("marker_position") for path in marker_paths}
    assert positions == {"start", "end"}

    start_fills = [
        path.fill
        for path in marker_paths
        if path.metadata.get("marker_position") == "start" and path.fill is not None
    ]
    assert any(isinstance(fill, SolidPaint) and fill.rgb.upper() == "00FF00" for fill in start_fills)
    assert all("marker_clip" in path.metadata for path in marker_paths)


def test_marker_viewbox_scaling_applied() -> None:
    svg = (
        "<svg width='40' height='40' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <marker id='box' markerWidth='6' markerHeight='6' viewBox='0 0 3 3' orient='auto'>"
        "    <path d='M0,0 L3,0 L3,3 z' overflow='visible'/>"
        "  </marker>"
        "</defs>"
        "<path d='M0 0 L10 0' stroke='#000000' stroke-width='1' marker-end='url(#box)' fill='none'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)
    scene = convert_parser_output(parse_result)

    marker_paths = [
        element
        for element in scene.elements
        if isinstance(element, Path) and element.metadata.get("marker_position") == "end"
    ]
    assert len(marker_paths) == 1
    marker_path = marker_paths[0]

    all_points = []
    for segment in marker_path.segments:
        if isinstance(segment, LineSegment):
            all_points.extend([segment.start, segment.end])
        elif isinstance(segment, BezierSegment):
            all_points.extend([segment.start, segment.control1, segment.control2, segment.end])

    xs = [point.x for point in all_points]
    ys = [point.y for point in all_points]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    assert pytest.approx(width, rel=1e-6) == pytest.approx(6.0)
    assert pytest.approx(height, rel=1e-6) == pytest.approx(6.0)

    clip = marker_path.metadata.get("marker_clip")
    assert clip == {"x": 0.0, "y": 0.0, "width": 6.0, "height": 6.0}
    viewbox_meta = marker_path.metadata.get("marker_viewbox")
    assert viewbox_meta == {"min_x": 0.0, "min_y": 0.0, "width": 3.0, "height": 3.0}
    assert marker_path.metadata.get("marker_overflow") == "hidden"


def test_marker_preserve_aspect_ratio_meet() -> None:
    svg = (
        "<svg width='60' height='60' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <marker id='arrow' markerWidth='10' markerHeight='4' markerUnits='userSpaceOnUse' viewBox='0 0 10 5' preserveAspectRatio='xMidYMid meet'>"
        "    <path d='M0,0 L10,0 L5,5 z'/>"
        "  </marker>"
        "</defs>"
        "<path d='M0 0 L20 0' stroke='#000' stroke-width='2' marker-end='url(#arrow)' fill='none'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)
    scene = convert_parser_output(parse_result)

    marker_paths = [
        element
        for element in scene.elements
        if isinstance(element, Path) and element.metadata.get("marker_position") == "end"
    ]
    assert len(marker_paths) == 1
    marker = marker_paths[0]

    clip = marker.metadata.get("marker_clip")
    assert clip == {"x": 0.0, "y": 0.0, "width": 10.0, "height": 4.0}

    # Geometry should be uniformly scaled (meet) based on the limiting dimension.
    xs = []
    ys = []
    for segment in marker.segments:
        if isinstance(segment, LineSegment):
            xs.extend([segment.start.x, segment.end.x])
            ys.extend([segment.start.y, segment.end.y])
        elif isinstance(segment, BezierSegment):
            xs.extend([segment.start.x, segment.control1.x, segment.control2.x, segment.end.x])
            ys.extend([segment.start.y, segment.control1.y, segment.control2.y, segment.end.y])
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    assert pytest.approx(width, rel=1e-6) == pytest.approx(8.0)
    assert pytest.approx(height, rel=1e-6) == pytest.approx(4.0)

def test_convert_path_produces_segments() -> None:
    parse_result = _build_parse_result(
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "<path d='M0 0 L10 0 L10 10 Z' fill='#00ff00'/>"
        "</svg>"
    )

    scene = convert_parser_output(parse_result)

    assert len(scene.elements) == 1
    path = scene.elements[0]
    assert isinstance(path, Path)
    assert len(path.segments) >= 3
    assert path.fill is not None


def test_convert_circle_produces_native_circle() -> None:
    parse_result = _build_parse_result(
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "<circle cx='50' cy='60' r='25' fill='#abcdef'/>"
        "</svg>"
    )

    scene = convert_parser_output(parse_result)

    circle = scene.elements[0]
    assert isinstance(circle, Circle)
    assert circle.center.x == pytest.approx(50.0)
    assert circle.center.y == pytest.approx(60.0)
    assert circle.radius == pytest.approx(25.0)
    assert circle.fill is not None and circle.fill.rgb == "ABCDEF"


def test_convert_ellipse_produces_native_ellipse() -> None:
    parse_result = _build_parse_result(
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "<ellipse cx='70' cy='80' rx='15' ry='10' fill='#fedcba'/>"
        "</svg>"
    )

    scene = convert_parser_output(parse_result)

    ellipse = scene.elements[0]
    assert isinstance(ellipse, Ellipse)
    assert ellipse.center.x == pytest.approx(70.0)
    assert ellipse.center.y == pytest.approx(80.0)
    assert ellipse.radius_x == pytest.approx(15.0)
    assert ellipse.radius_y == pytest.approx(10.0)
    assert ellipse.fill is not None and ellipse.fill.rgb == "FEDCBA"


def test_emf_fallback_creates_image() -> None:
    parse_result = _build_parse_result(
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "<path d='M0 0 L10 0 L10 10 L0 10 Z' fill='#000000'/>"
        "</svg>"
    )
    services = configure_services()
    policy_context = PolicyContext(selections={"geometry": {"max_segments": 2, "simplify_paths": False}})
    converter = IRConverter(services=services, policy_context=policy_context)

    scene = converter.convert(parse_result)

    assert isinstance(scene.elements[0], Image)
    assert scene.elements[0].format == "emf"
    assert scene.elements[0].data and scene.elements[0].data[:4] == b"\x01\x00\x00\x00"
    emf_meta = scene.elements[0].metadata.get("emf_asset")
    assert isinstance(emf_meta, dict)
    assert emf_meta.get("width_emu") and emf_meta.get("height_emu")


def test_bitmap_fallback_creates_png() -> None:
    pytest.importorskip("PIL.Image")
    parse_result = _build_parse_result(
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "<path d='M0 0 L10 0 L10 10 L0 10 Z' fill='#0000ff'/>"
        "</svg>"
    )
    services = configure_services()
    policy_context = PolicyContext(selections={"geometry": {"force_bitmap": True}})
    converter = IRConverter(services=services, policy_context=policy_context)

    scene = converter.convert(parse_result)

    assert isinstance(scene.elements[0], Image)
    assert scene.elements[0].format == "png"
    assert scene.elements[0].data and scene.elements[0].data.startswith(b"\x89PNG")


def test_bitmap_fallback_respects_side_limit() -> None:
    pytest.importorskip("PIL.Image")
    parse_result = _build_parse_result(
        "<svg width='4000' height='4000' xmlns='http://www.w3.org/2000/svg'>"
        "<path d='M0 0 L2500 0 L2500 1000 L0 1000 Z' fill='#ff0000'/>"
        "</svg>"
    )
    services = configure_services()
    policy_context = PolicyContext(
        selections={"geometry": {"force_bitmap": True, "max_bitmap_side": 500}}
    )
    converter = IRConverter(services=services, policy_context=policy_context)

    scene = converter.convert(parse_result)

    assert isinstance(scene.elements[0], Path)
    geometry_meta = scene.elements[0].metadata.get("policy", {}).get("geometry", {})
    assert geometry_meta.get("bitmap_suppressed") == "max_side"
    assert geometry_meta.get("bitmap_limit_side") == 500
    assert geometry_meta.get("bitmap_target_size") is not None


def test_bitmap_fallback_respects_area_limit() -> None:
    pytest.importorskip("PIL.Image")
    parse_result = _build_parse_result(
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "<path d='M0 0 L60 0 L60 60 L0 60 Z' fill='#00ff88'/>"
        "</svg>"
    )
    services = configure_services()
    policy_context = PolicyContext(
        selections={"geometry": {"force_bitmap": True, "max_bitmap_area": 2500, "max_bitmap_side": 1000}}
    )
    converter = IRConverter(services=services, policy_context=policy_context)

    scene = converter.convert(parse_result)

    assert isinstance(scene.elements[0], Path)
    geometry_meta = scene.elements[0].metadata.get("policy", {}).get("geometry", {})
    assert geometry_meta.get("bitmap_suppressed") == "max_area"
    assert geometry_meta.get("bitmap_limit_area") == 2500
