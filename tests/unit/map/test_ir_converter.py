"""Tests for the IR converter pipeline."""

from __future__ import annotations

import math
from pathlib import Path as FilePath

import pytest
from lxml import etree

from svg2ooxml.core.ir import IRConverter, IRScene
from svg2ooxml.core.parser import ParseResult
from svg2ooxml.core.parser import ParserConfig, SVGParser
from svg2ooxml.ir.entrypoints import convert_parser_output
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect
from svg2ooxml.ir.paint import (
    GradientPaintRef,
    LinearGradientPaint,
    PatternPaint,
    SolidPaint,
    Stroke,
)
from svg2ooxml.ir.scene import Group, Image, Path
from svg2ooxml.ir.shapes import Circle, Ellipse, Rectangle
from svg2ooxml.ir.text import TextFrame
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


def _convert_with_resvg(parse_result: ParseResult) -> IRScene:
    return convert_parser_output(
        parse_result,
        overrides={"geometry": {"geometry_mode": "resvg-only"}},
    )


def _unwrap_use_rectangle(element: object) -> tuple[Rectangle, dict[str, object]]:
    if isinstance(element, Group):
        rect = next(child for child in element.children if isinstance(child, Rectangle))
        metadata = (
            element.metadata
            if isinstance(element.metadata, dict)
            and element.metadata.get("element_ids")
            else rect.metadata
        )
        return rect, metadata
    assert isinstance(element, Rectangle)
    return element, element.metadata


def _collect_rectangles(elements: list[object]) -> list[Rectangle]:
    rectangles: list[Rectangle] = []
    stack = list(elements)
    while stack:
        current = stack.pop()
        if isinstance(current, Rectangle):
            rectangles.append(current)
            continue
        if isinstance(current, Group):
            stack.extend(current.children)
    return rectangles


def _fixture_path(name: str) -> FilePath:
    return FilePath(__file__).resolve().parents[2] / "visual" / "fixtures" / name


def _convert_fixture_with_resvg(name: str) -> IRScene:
    fixture = _fixture_path(name)
    parser = SVGParser(ParserConfig())
    result = parser.parse(fixture.read_text(), source_path=str(fixture))
    return convert_parser_output(
        result,
        overrides={"geometry": {"geometry_mode": "resvg-only"}},
    )


def test_scene_metadata_preserves_source_path() -> None:
    svg = "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'><rect width='10' height='10'/></svg>"
    parser = SVGParser(ParserConfig())
    result = parser.parse(
        svg,
        source_path="/tmp/project/tests/svg/sample.svg",
    )

    scene = convert_parser_output(result)

    assert scene.metadata is not None
    assert scene.metadata["source_path"] == "/tmp/project/tests/svg/sample.svg"


def _iter_scene_elements(element: object):
    if isinstance(element, Group):
        yield element
        for child in element.children:
            yield from _iter_scene_elements(child)
        return
    yield element


def _element_ids(element: object) -> list[str]:
    metadata = getattr(element, "metadata", None)
    if not isinstance(metadata, dict):
        return []
    element_ids = metadata.get("element_ids")
    if isinstance(element_ids, list) and element_ids:
        return [str(element_id) for element_id in element_ids]
    return []


def _register_filter(parse_result: ParseResult, filter_markup: str) -> None:
    filters = parse_result.filters or {}
    element = etree.fromstring(filter_markup)
    filter_id = element.get("id", "filter")
    filters[filter_id] = element
    parse_result.filters = filters  # type: ignore[assignment]


def _path_points(path: Path) -> list[Point]:
    points: list[Point] = []
    for segment in path.segments:
        if isinstance(segment, LineSegment):
            points.extend([segment.start, segment.end])
        elif isinstance(segment, BezierSegment):
            points.extend(
                [segment.start, segment.control1, segment.control2, segment.end]
            )
    return points


def _eu_flag_star_ring_svg() -> str:
    return (
        "<svg width='810' height='540' xmlns='http://www.w3.org/2000/svg' "
        "xmlns:xlink='http://www.w3.org/1999/xlink'>"
        "<defs>"
        "  <g id='s'>"
        "    <g id='c'>"
        "      <path id='t' d='M0,0v1h0.5z' transform='translate(0,-1)rotate(18)'/>"
        "      <use href='#t' transform='scale(-1,1)'/>"
        "    </g>"
        "    <g id='a'>"
        "      <use href='#c' transform='rotate(72)'/>"
        "      <use href='#c' transform='rotate(144)'/>"
        "    </g>"
        "    <use href='#a' transform='scale(-1,1)'/>"
        "  </g>"
        "</defs>"
        "<g fill='#fc0' transform='scale(30)translate(13.5,9)'>"
        "  <use href='#s' y='-6'/>"
        "  <use href='#s' y='6'/>"
        "  <g id='l'>"
        "    <use href='#s' x='-6'/>"
        "    <use href='#s' transform='rotate(150)translate(0,6)rotate(66)'/>"
        "    <use href='#s' transform='rotate(120)translate(0,6)rotate(24)'/>"
        "    <use href='#s' transform='rotate(60)translate(0,6)rotate(12)'/>"
        "    <use href='#s' transform='rotate(30)translate(0,6)rotate(42)'/>"
        "  </g>"
        "  <use href='#l' transform='scale(-1,1)'/>"
        "</g>"
        "</svg>"
    )


def _count_paths(element: object) -> int:
    if isinstance(element, Path):
        return 1
    if isinstance(element, Group):
        return sum(_count_paths(child) for child in element.children)
    return 0


def _collect_paths(element: object) -> list[Path]:
    if isinstance(element, Path):
        return [element]
    if isinstance(element, Group):
        paths: list[Path] = []
        for child in element.children:
            paths.extend(_collect_paths(child))
        return paths
    return []


def _collect_groups_with_path_count(element: object, path_count: int) -> list[Group]:
    if isinstance(element, Group) and _count_paths(element) == path_count:
        return [element]
    if isinstance(element, Group):
        groups: list[Group] = []
        for child in element.children:
            groups.extend(_collect_groups_with_path_count(child, path_count))
        return groups
    return []


def _group_center(group: Group) -> tuple[float, float]:
    points = [point for path in _collect_paths(group) for point in _path_points(path)]
    return (
        sum(point.x for point in points) / len(points),
        sum(point.y for point in points) / len(points),
    )


def _has_point(
    points: list[Point], x: float, y: float, *, tolerance: float = 1e-6
) -> bool:
    return any(
        abs(point.x - x) <= tolerance and abs(point.y - y) <= tolerance
        for point in points
    )


def test_convert_rect_produces_rectangle() -> None:
    parse_result = _build_parse_result(
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "<rect x='10' y='20' width='30' height='40' fill='#ff0000'/>"
        "</svg>"
    )

    scene = _convert_with_resvg(parse_result)

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

    scene = _convert_with_resvg(parse_result)

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

    scene = _convert_with_resvg(parse_result)

    shape = scene.elements[0]
    assert isinstance(shape, Path)
    assert len(shape.segments) == 1
    segment = shape.segments[0]
    assert segment.start.x == pytest.approx(5.0)
    assert segment.end.y == pytest.approx(26.0)
    assert shape.stroke is not None and shape.stroke.paint.rgb == "123456"


def test_convert_polyline_produces_native_polyline() -> None:
    parse_result = _build_parse_result(
        "<svg width='100' height='100' xmlns='http://www.w3.org/2000/svg'>"
        "<polyline points='0,0 10,10 20,0' stroke='#00AAFF' stroke-width='1.5' fill='none'/>"
        "</svg>"
    )

    scene = _convert_with_resvg(parse_result)

    shape = scene.elements[0]
    assert isinstance(shape, Path)
    assert len(shape.segments) == 2
    assert shape.segments[0].end.x == pytest.approx(10.0)
    assert shape.stroke is not None and shape.stroke.paint.rgb == "00AAFF"


def test_convert_polygon_produces_native_polygon() -> None:
    parse_result = _build_parse_result(
        "<svg width='100' height='100' xmlns='http://www.w3.org/2000/svg'>"
        "<polygon points='10,10 30,10 20,25' fill='#AA5500' stroke='#002244'/>"
        "</svg>"
    )

    scene = _convert_with_resvg(parse_result)

    shape = scene.elements[0]
    assert isinstance(shape, Path)
    assert len(shape.segments) == 3
    assert shape.segments[0].start.x == pytest.approx(10.0)
    assert shape.fill is not None and shape.fill.rgb == "AA5500"


def test_convert_rect_preserves_explicit_fill_none_with_stroke() -> None:
    parse_result = _build_parse_result(
        "<svg width='100' height='100' xmlns='http://www.w3.org/2000/svg'>"
        "<rect x='10' y='10' width='40' height='30' fill='none' stroke='#0000FF' stroke-width='0.5'/>"
        "</svg>"
    )

    scene = _convert_with_resvg(parse_result)

    shape = scene.elements[0]
    assert isinstance(shape, Rectangle)
    assert shape.fill is None
    assert shape.stroke is not None and shape.stroke.paint.rgb == "0000FF"


def test_convert_rotated_rounded_rect_generates_bezier_path() -> None:
    parse_result = _build_parse_result(
        "<svg width='120' height='120' xmlns='http://www.w3.org/2000/svg'>"
        "<rect x='10' y='15' width='40' height='25' rx='5' transform='rotate(30 30 27.5)'/>"
        "</svg>"
    )

    scene = _convert_with_resvg(parse_result)

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

    scene = _convert_with_resvg(parse_result)

    assert len(scene.elements) == 1
    rect, metadata = _unwrap_use_rectangle(scene.elements[0])
    assert rect.bounds.x == pytest.approx(5.0)
    assert rect.bounds.y == pytest.approx(7.0)
    assert rect.bounds.width == pytest.approx(10.0)
    assert rect.bounds.height == pytest.approx(20.0)
    assert rect.fill is not None and rect.fill.rgb == "010203"
    element_ids = set(metadata.get("element_ids", []))
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

    scene = _convert_with_resvg(parse_result)

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

    scene = _convert_with_resvg(parse_result)

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

    scene = _convert_with_resvg(parse_result)

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

    scene = _convert_with_resvg(parse_result)

    assert len(scene.elements) == 2
    first_rect = scene.elements[0]
    assert isinstance(first_rect, Rectangle)
    assert first_rect.bounds.x == pytest.approx(0.0)
    assert first_rect.bounds.y == pytest.approx(0.0)

    # Plain-element <use> references should honor x/y offsets as well.
    second_rect, metadata = _unwrap_use_rectangle(scene.elements[1])
    assert second_rect.bounds.x == pytest.approx(25.0)
    assert second_rect.bounds.y == pytest.approx(35.0)
    assert second_rect.bounds.width == pytest.approx(8.0)
    assert second_rect.bounds.height == pytest.approx(9.0)
    assert second_rect.fill is not None and second_rect.fill.rgb == "FF00FF"
    element_ids = set(metadata.get("element_ids", []))
    assert "copyRect" in element_ids


def test_use_group_preserves_child_fill_none() -> None:
    parse_result = _build_parse_result(
        "<svg width='160' height='160' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <g id='outlines'>"
        "    <rect x='0' y='0' width='8' height='9' fill='none' stroke='#0000FF'/>"
        "    <rect x='2' y='2' width='10' height='11' fill='none' stroke='#0000FF'/>"
        "  </g>"
        "</defs>"
        "<use id='outlineCopy' href='#outlines' x='25' y='35'/>"
        "</svg>"
    )

    scene = _convert_with_resvg(parse_result)

    assert len(scene.elements) == 1
    group = scene.elements[0]
    assert isinstance(group, Group)
    rectangles = _collect_rectangles(group.children)
    assert len(rectangles) == 2
    assert all(rect.fill is None for rect in rectangles)
    assert all(rect.stroke is not None and rect.stroke.paint.rgb == "0000FF" for rect in rectangles)


def test_use_image_expands_when_resvg_use_node_is_unsupported() -> None:
    parse_result = _build_parse_result(
        "<svg width='160' height='160' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <image id='baseImage' href='https://example.com/foo.png' x='20' y='25' width='10' height='8'/>"
        "</defs>"
        "<use id='imageUse' href='#baseImage'/>"
        "</svg>"
    )

    scene = _convert_with_resvg(parse_result)

    assert len(scene.elements) == 1
    image = scene.elements[0]
    assert isinstance(image, Image)
    assert image.href == "https://example.com/foo.png"
    assert "imageUse" in set(image.metadata.get("element_ids", []))


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

    scene = _convert_with_resvg(parse_result)

    assert len(scene.elements) == 1
    rect, _ = _unwrap_use_rectangle(scene.elements[0])
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

    scene = _convert_with_resvg(parse_result)

    rect, _ = _unwrap_use_rectangle(scene.elements[0])
    assert rect.bounds.width == pytest.approx(20.0)
    assert rect.bounds.height == pytest.approx(10.0)


def test_use_symbol_viewbox_meet_positions_without_scaling_use_offsets() -> None:
    parse_result = _build_parse_result(
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <symbol id='vbSymbol' viewBox='0 0 10 10'>"
        "    <rect width='10' height='10'/>"
        "  </symbol>"
        "</defs>"
        "<use id='scaled' href='#vbSymbol' x='50' y='60' width='20' height='40'/>"
        "</svg>"
    )

    scene = _convert_with_resvg(parse_result)

    rect, _ = _unwrap_use_rectangle(scene.elements[0])
    assert rect.bounds.x == pytest.approx(50.0)
    assert rect.bounds.y == pytest.approx(70.0)
    assert rect.bounds.width == pytest.approx(20.0)
    assert rect.bounds.height == pytest.approx(20.0)


def test_use_symbol_viewbox_none_applies_transform_after_positioning() -> None:
    parse_result = _build_parse_result(
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <symbol id='vbSymbol' viewBox='0 0 10 10'>"
        "    <rect width='10' height='10'/>"
        "  </symbol>"
        "</defs>"
        "<use id='scaled' href='#vbSymbol' x='50' y='60' width='20' height='40' preserveAspectRatio='none' transform='translate(5,7)'/>"
        "</svg>"
    )

    scene = _convert_with_resvg(parse_result)

    rect, _ = _unwrap_use_rectangle(scene.elements[0])
    assert rect.bounds.x == pytest.approx(55.0)
    assert rect.bounds.y == pytest.approx(67.0)
    assert rect.bounds.width == pytest.approx(20.0)
    assert rect.bounds.height == pytest.approx(40.0)


def test_mirrored_nested_use_preserves_asymmetric_child_positions() -> None:
    parse_result = _build_parse_result(
        "<svg width='100' height='50' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <rect id='leaf' width='2' height='3'/>"
        "  <g id='half'>"
        "    <use href='#leaf' x='3' y='1'/>"
        "    <use href='#leaf' x='8' y='4'/>"
        "  </g>"
        "</defs>"
        "<use href='#half'/>"
        "<use href='#half' transform='matrix(-1 0 0 1 20 0)'/>"
        "</svg>"
    )

    scene = _convert_with_resvg(parse_result)
    rects = _collect_rectangles(scene.elements)

    observed = sorted(
        (rect.bounds.x, rect.bounds.y, rect.bounds.width, rect.bounds.height)
        for rect in rects
    )
    assert observed == [
        (3.0, 1.0, 2.0, 3.0),
        (8.0, 4.0, 2.0, 3.0),
        (10.0, 4.0, 2.0, 3.0),
        (15.0, 1.0, 2.0, 3.0),
    ]


def test_nested_use_ring_preserves_outer_group_translation() -> None:
    parse_result = _build_parse_result(
        "<svg width='100' height='100' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <rect id='leaf' width='2' height='2'/>"
        "  <g id='ring'>"
        "    <use href='#leaf' x='10' y='0'/>"
        "    <use href='#leaf' x='0' y='10'/>"
        "    <use href='#leaf' x='-10' y='0'/>"
        "    <use href='#leaf' x='0' y='-10'/>"
        "  </g>"
        "</defs>"
        "<g transform='translate(40,40)'><use href='#ring'/></g>"
        "</svg>"
    )

    scene = _convert_with_resvg(parse_result)
    rects = _collect_rectangles(scene.elements)

    observed = sorted((rect.bounds.x, rect.bounds.y) for rect in rects)
    assert observed == [
        (30.0, 40.0),
        (40.0, 30.0),
        (40.0, 50.0),
        (50.0, 40.0),
    ]


def test_eu_flag_ring_expands_to_twelve_ten_wedge_stars() -> None:
    parse_result = _build_parse_result(_eu_flag_star_ring_svg())

    scene = _convert_with_resvg(parse_result)

    assert len(scene.elements) == 1
    root = scene.elements[0]
    assert isinstance(root, Group)

    star_groups = _collect_groups_with_path_count(root, 10)
    assert len(star_groups) == 12
    assert all(_count_paths(group) == 10 for group in star_groups)

    expected_centers = sorted(
        (
            round(405.0 + 180.0 * math.cos(math.radians(angle)), 3),
            round(270.0 + 180.0 * math.sin(math.radians(angle)), 3),
        )
        for angle in range(-90, 270, 30)
    )
    observed_centers = sorted(
        (
            round(center[0], 3),
            round(center[1], 3),
        )
        for center in [_group_center(group) for group in star_groups]
    )

    assert observed_centers == expected_centers

    all_points = [
        point
        for group in star_groups
        for path in _collect_paths(group)
        for point in _path_points(path)
    ]
    assert all(0.0 <= point.x <= 810.0 for point in all_points)
    assert all(0.0 <= point.y <= 540.0 for point in all_points)


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

    scene = _convert_with_resvg(parse_result)

    assert len(scene.elements) == 1
    shape = scene.elements[0]
    assert hasattr(shape, "metadata")
    filter_meta = shape.metadata.get("filter_metadata", {})
    assert "glow" in filter_meta
    assets = filter_meta["glow"].get("fallback_assets")
    media_policy = shape.metadata.get("policy", {}).get("media", {})
    filter_assets = media_policy.get("filter_assets", {})
    if assets:
        assert any(asset.get("type") in {"emf", "raster"} for asset in assets)
        assert "glow" in filter_assets
    else:
        assert "glow" not in filter_assets


def test_native_filter_chain_carries_aggregate_raster_fallback() -> None:
    svg = (
        "<svg width='120' height='120' xmlns='http://www.w3.org/2000/svg'>"
        "  <defs>"
        "    <filter id='glow'>"
        "      <feFlood flood-color='#112233' flood-opacity='0.7' result='flood'/>"
        "      <feGaussianBlur in='flood' stdDeviation='3' result='halo'/>"
        "      <feMerge>"
        "        <feMergeNode in='halo'/>"
        "        <feMergeNode in='SourceGraphic'/>"
        "      </feMerge>"
        "    </filter>"
        "  </defs>"
        "  <rect id='shape' x='10' y='10' width='40' height='40' filter='url(#glow)'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)
    _register_filter(
        parse_result,
        "<filter id='glow'>"
        "  <feFlood flood-color='#112233' flood-opacity='0.7' result='flood'/>"
        "  <feGaussianBlur in='flood' stdDeviation='3' result='halo'/>"
        "  <feMerge>"
        "    <feMergeNode in='halo'/>"
        "    <feMergeNode in='SourceGraphic'/>"
        "  </feMerge>"
        "</filter>",
    )

    scene = convert_parser_output(
        parse_result,
        overrides={
            "geometry": {"geometry_mode": "resvg-only"},
            "filter": {"strategy": "native", "approximation_allowed": False},
        },
    )

    assert len(scene.elements) == 1
    shape = scene.elements[0]
    assert hasattr(shape, "metadata")
    filters_meta = shape.metadata.get("filters", [])
    entry = next(item for item in filters_meta if item.get("id") == "glow")
    assert entry["fallback"] in {FALLBACK_BITMAP, "raster"}
    filter_meta = shape.metadata.get("filter_metadata", {}).get("glow", {})
    assert filter_meta.get("fallback") in {FALLBACK_BITMAP, "raster"}
    assets = filter_meta.get("fallback_assets")
    assert isinstance(assets, list) and assets
    assert any(asset.get("type") == "raster" for asset in assets)
    media_policy = shape.metadata.get("policy", {}).get("media", {})
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

    scene = _convert_with_resvg(parse_result)

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
    scene = _convert_with_resvg(parse_result)

    rect = scene.elements[0]
    assert isinstance(rect, Rectangle)
    assert isinstance(rect.fill, GradientPaintRef)
    assert rect.fill.gradient_id == "meshGrad"
    assert rect.fill.gradient_type == "mesh"
    analysis = rect.metadata.get("paint_analysis", {}).get("fill", {}).get("gradient")
    assert analysis is not None
    assert analysis["type"] == "mesh"
    assert analysis["patch_count"] == 2
    paint_policy = rect.metadata.get("policy", {}).get("paint", {}).get("fill", {})
    assert paint_policy.get("gradient_kind") == "mesh"
    assert paint_policy.get("suggest_fallback") == FALLBACK_EMF
    geometry_policy = rect.metadata.get("policy", {}).get("geometry", {})
    assert geometry_policy.get("suggest_fallback") == FALLBACK_EMF


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

    scene = _convert_with_resvg(parse_result)

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

    scene = _convert_with_resvg(parse_result)

    text = scene.elements[0]
    assert isinstance(text, TextFrame)
    resvg_text = text.metadata.get("resvg_text", {})
    assert isinstance(resvg_text, dict)
    assert resvg_text.get("strategy") in {"runs", "emf", "error", "empty"}
    if resvg_text.get("strategy") == "runs":
        runs_xml = resvg_text.get("runs_xml", "")
        assert "Bold" in runs_xml
        assert "Green" in runs_xml


def test_textpath_metadata_captured() -> None:
    svg = (
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "<defs><path id='curve' d='M0 40 Q 25 0 50 40'/></defs>"
        "<text><textPath href='#curve'>Hello</textPath></text>"
        "</svg>"
    )
    parse_result = _build_parse_result(svg)

    scene = _convert_with_resvg(parse_result)

    assert len(scene.elements) == 1
    text = scene.elements[0]
    assert isinstance(text, TextFrame)
    assert text.wordart_candidate is not None
    assert text.metadata.get("text_path_id") == "curve"
    resvg_text = text.metadata.get("resvg_text", {})
    assert isinstance(resvg_text, dict)
    assert resvg_text.get("strategy") == "text_path"


def test_inline_navigation_attributes_attach_metadata() -> None:
    svg = (
        "<svg width='100' height='60' xmlns='http://www.w3.org/2000/svg'>"
        "  <rect width='20' height='10' fill='#ff00ff' data-slide='3' title='Jump'/>"
        "</svg>"
    )
    parse_result = _build_parse_result(svg)

    scene = _convert_with_resvg(parse_result)

    rect = scene.elements[0]
    assert isinstance(rect, Rectangle)
    navigation = rect.metadata.get("navigation")
    assert navigation is not None
    assert navigation["kind"] == "slide"
    assert navigation["slide"]["index"] == 3
    assert rect.metadata.get("attributes", {}).get("title") == "Jump"


def test_group_navigation_attributes_propagate_to_children() -> None:
    svg = (
        "<svg width='120' height='80' xmlns='http://www.w3.org/2000/svg'>"
        "  <g data-custom-show='deckA'>"
        "    <rect id='card' width='30' height='15' fill='#00aaff' />"
        "  </g>"
        "</svg>"
    )
    parse_result = _build_parse_result(svg)

    scene = _convert_with_resvg(parse_result)

    group = scene.elements[0]
    assert isinstance(group, Group)
    nav = group.metadata.get("navigation")
    assert nav is not None
    assert nav["kind"] == "custom_show"
    assert nav["custom_show"]["name"] == "deckA"

    child = group.children[0]
    assert isinstance(child, Rectangle)
    child_nav = child.metadata.get("navigation")
    assert child_nav is not None
    assert child_nav["custom_show"]["name"] == "deckA"


def test_interactive_annotation_fixture_preserves_hotspot_navigation_and_labels() -> (
    None
):
    scene = _convert_fixture_with_resvg("interactive_annotation.svg")

    elements_by_id: dict[str, object] = {}
    for root in scene.elements:
        for element in _iter_scene_elements(root):
            for element_id in _element_ids(element):
                elements_by_id[element_id] = element

    start_hotspot = elements_by_id["step_start_hotspot"]
    branch_hotspot = elements_by_id["step_branch_hotspot"]
    resolve_hotspot = elements_by_id["step_resolve_hotspot"]
    start_label = elements_by_id["label_start"]
    branch_label = elements_by_id["label_branch"]
    resolve_label = elements_by_id["label_resolve"]

    assert isinstance(start_hotspot, Path)
    assert isinstance(branch_hotspot, Path)
    assert isinstance(resolve_hotspot, Path)
    assert isinstance(start_label, TextFrame)
    assert isinstance(branch_label, TextFrame)
    assert isinstance(resolve_label, TextFrame)

    assert start_hotspot.metadata["navigation"]["slide"]["index"] == 2
    assert branch_hotspot.metadata["navigation"]["slide"]["index"] == 3
    assert resolve_hotspot.metadata["navigation"]["slide"]["index"] == 4

    assert start_label.runs[0].text == "Start"
    assert branch_label.runs[0].text == "Branch"
    assert resolve_label.runs[0].text == "Resolve"

    assert start_label.bbox.x > start_hotspot.bbox.x + start_hotspot.bbox.width
    assert branch_label.bbox.x > branch_hotspot.bbox.x + branch_hotspot.bbox.width
    assert resolve_label.bbox.x > resolve_hotspot.bbox.x + resolve_hotspot.bbox.width


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

    scene = _convert_with_resvg(parse_result)

    shape = scene.elements[0]
    assert hasattr(shape, "metadata")
    filters_meta = shape.metadata.get("filters")
    assert isinstance(filters_meta, list)
    entry = next(iter(filters_meta))
    assert entry["id"] == "glow"
    assert entry["strategy"] in {"native", "raster", "auto", "resvg"}
    # Entry may omit fallback when a native strategy is selected
    if entry.get("fallback"):
        assert entry["fallback"] in {"bitmap", "emf", "vector"}
    geometry_policy = shape.metadata.get("policy", {}).get("geometry", {})
    if "suggest_fallback" in geometry_policy:
        assert geometry_policy["suggest_fallback"] in {FALLBACK_BITMAP, "emf", "vector"}
    assert shape.effects, "expected filter to add custom effects"
    filters_policy = (
        shape.metadata.get("policy", {}).get("effects", {}).get("filters", [])
    )
    assert any(item.get("id") == "glow" for item in filters_policy)


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

    scene = _convert_with_resvg(parse_result)

    shape = scene.elements[0]
    assert hasattr(shape, "metadata")
    filters_meta = shape.metadata.get("filters", [])
    assert any(entry.get("id") == "disp" for entry in filters_meta)
    filter_meta = shape.metadata.get("filter_metadata", {}).get("disp", {})
    assert filter_meta is not None
    geometry_policy = shape.metadata.get("policy", {}).get("geometry", {})
    if "suggest_fallback" in geometry_policy:
        assert geometry_policy["suggest_fallback"] in {
            FALLBACK_BITMAP,
            FALLBACK_EMF,
            "vector",
        }
    filters_policy = (
        shape.metadata.get("policy", {}).get("effects", {}).get("filters", [])
    )
    assert any(item.get("id") == "disp" for item in filters_policy)


def test_style_based_filter_metadata_adds_effects() -> None:
    svg = (
        "<svg width='40' height='40' xmlns='http://www.w3.org/2000/svg'>"
        "  <defs>"
        "    <filter id='glow'><feGaussianBlur stdDeviation='5'/></filter>"
        "  </defs>"
        "  <rect width='20' height='10' "
        "style='fill:#ff0000;filter:url(#glow)'/>"
        "</svg>"
    )
    parse_result = _build_parse_result(svg)

    scene = _convert_with_resvg(parse_result)

    shape = scene.elements[0]
    assert hasattr(shape, "metadata")
    filters_meta = shape.metadata.get("filters", [])
    assert any(entry.get("id") == "glow" for entry in filters_meta)
    assert shape.effects, "expected inline style filter to add custom effects"
    filters_policy = (
        shape.metadata.get("policy", {}).get("effects", {}).get("filters", [])
    )
    assert any(item.get("id") == "glow" for item in filters_policy)


def test_grouped_gaussian_blur_policy_override_attaches_mimic_effects() -> None:
    svg = (
        "<svg width='480' height='360' viewBox='0 0 480 360' "
        "xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink'>"
        "  <defs>"
        "    <g id='rects'>"
        "      <rect x='0' y='0' width='90' height='90' fill='blue'/>"
        "      <rect x='45' y='45' width='90' height='90' fill='yellow'/>"
        "    </g>"
        "    <filter id='blur'>"
        "      <feGaussianBlur stdDeviation='10'/>"
        "    </filter>"
        "  </defs>"
        "  <g transform='translate(310,15)'>"
        "    <use xlink:href='#rects' filter='url(#blur)'/>"
        "  </g>"
        "</svg>"
    )

    parser = SVGParser(ParserConfig())
    parse_result = parser.parse(svg)

    scene = convert_parser_output(
        parse_result,
        services=parse_result.services,
        overrides={
            "geometry": {"geometry_mode": "resvg-only"},
            "filter": {
                "strategy": "native",
                "approximation_allowed": True,
                "prefer_rasterization": False,
                "blur_strategy": "soft_edge",
                "primitives": {
                    "fegaussianblur": {
                        "allow_group_mimic": True,
                        "group_blur_strategy": "blur",
                    }
                },
            },
        },
    )

    filtered_groups: list[Group] = []
    filtered_paths: list[Path] = []

    def _walk(node: object) -> None:
        if isinstance(node, Group):
            metadata = node.metadata if isinstance(node.metadata, dict) else {}
            if metadata.get("filter_metadata"):
                filtered_groups.append(node)
            for child in node.children:
                _walk(child)
            return
        if isinstance(node, Path):
            effects = getattr(node, "effects", None) or []
            if any(getattr(effect, "drawingml", "") for effect in effects):
                filtered_paths.append(node)

    for element in scene.elements:
        _walk(element)

    assert filtered_groups, "expected converted group filter metadata"
    group_meta = filtered_groups[0].metadata["filter_metadata"]["blur"]
    assert group_meta["approximation"] == "group_per_child"
    assert group_meta["mimic_scope"] == "group_children"

    assert filtered_paths, "expected child paths to receive blur effects"
    effect_xml = [
        getattr(effect, "drawingml", "")
        for path in filtered_paths
        for effect in (path.effects or [])
        if getattr(effect, "drawingml", "")
    ]
    assert any("<a:blur " in xml for xml in effect_xml)
    assert not any("Group Gaussian blur rendered via raster fallback" in xml for xml in effect_xml)


def test_grouped_diffuse_lighting_policy_override_attaches_mimic_effects() -> None:
    svg = (
        "<svg width='480' height='360' viewBox='0 0 480 360' "
        "xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink'>"
        "  <defs>"
        "    <g id='bars'>"
        "      <rect x='0' y='0' width='70' height='90' rx='12' fill='#355070'/>"
        "      <rect x='84' y='0' width='70' height='90' rx='12' fill='#6D597A'/>"
        "    </g>"
        "    <filter id='lit'>"
        "      <feDiffuseLighting in='SourceAlpha' surfaceScale='4' diffuseConstant='1.2' lighting-color='#CDEBFF' result='light'>"
        "        <feDistantLight azimuth='20' elevation='35'/>"
        "      </feDiffuseLighting>"
        "      <feComposite in='light' in2='SourceGraphic' operator='arithmetic' k2='1' k3='1'/>"
        "    </filter>"
        "  </defs>"
        "  <g transform='translate(150,40)'>"
        "    <use xlink:href='#bars' filter='url(#lit)'/>"
        "  </g>"
        "</svg>"
    )

    parser = SVGParser(ParserConfig())
    parse_result = parser.parse(svg)

    scene = convert_parser_output(
        parse_result,
        services=parse_result.services,
        overrides={
            "geometry": {"geometry_mode": "resvg-only"},
            "filter": {
                "strategy": "native",
                "approximation_allowed": True,
                "prefer_rasterization": False,
            },
        },
    )

    filtered_groups: list[Group] = []
    effected_nodes: list[object] = []

    def _walk(node: object) -> None:
        if isinstance(node, Group):
            metadata = node.metadata if isinstance(node.metadata, dict) else {}
            if metadata.get("filter_metadata"):
                filtered_groups.append(node)
            for child in node.children:
                _walk(child)
            return
        effects = getattr(node, "effects", None) or []
        if any(getattr(effect, "drawingml", "") for effect in effects):
            effected_nodes.append(node)

    for element in scene.elements:
        _walk(element)

    assert filtered_groups, "expected converted group filter metadata"
    group_meta = filtered_groups[0].metadata["filter_metadata"]["lit"]
    assert group_meta["stack_type"] == "diffuse_lighting_composite"

    assert effected_nodes, "expected child shapes to receive lighting effects"
    effect_xml = [
        getattr(effect, "drawingml", "")
        for node in effected_nodes
        for effect in (getattr(node, "effects", None) or [])
        if getattr(effect, "drawingml", "")
    ]
    assert any("<a:fillOverlay" in xml for xml in effect_xml)
    assert any("<a:innerShdw" in xml for xml in effect_xml)


def test_grouped_specular_lighting_policy_override_attaches_mimic_effects() -> None:
    svg = (
        "<svg width='480' height='360' viewBox='0 0 480 360' "
        "xmlns='http://www.w3.org/2000/svg' xmlns:xlink='http://www.w3.org/1999/xlink'>"
        "  <defs>"
        "    <g id='chips'>"
        "      <rect x='0' y='0' width='160' height='90' rx='45' fill='#335C67'/>"
        "      <circle cx='48' cy='42' r='12' fill='#FFFFFF' opacity='0.2'/>"
        "    </g>"
        "    <filter id='spec'>"
        "      <feSpecularLighting in='SourceAlpha' surfaceScale='5' specularConstant='1.1' specularExponent='24' lighting-color='#DFF4FF' result='light'>"
        "        <feDistantLight azimuth='25' elevation='38'/>"
        "      </feSpecularLighting>"
        "      <feComposite in='light' in2='SourceGraphic' operator='arithmetic' k2='1' k3='1'/>"
        "    </filter>"
        "  </defs>"
        "  <g transform='translate(140,60)'>"
        "    <use xlink:href='#chips' filter='url(#spec)'/>"
        "  </g>"
        "</svg>"
    )

    parser = SVGParser(ParserConfig())
    parse_result = parser.parse(svg)

    scene = convert_parser_output(
        parse_result,
        services=parse_result.services,
        overrides={
            "geometry": {"geometry_mode": "resvg-only"},
            "filter": {
                "strategy": "native",
                "approximation_allowed": True,
                "prefer_rasterization": False,
            },
        },
    )

    filtered_groups: list[Group] = []
    effected_nodes: list[object] = []

    def _walk(node: object) -> None:
        if isinstance(node, Group):
            metadata = node.metadata if isinstance(node.metadata, dict) else {}
            if metadata.get("filter_metadata"):
                filtered_groups.append(node)
            for child in node.children:
                _walk(child)
            return
        effects = getattr(node, "effects", None) or []
        if any(getattr(effect, "drawingml", "") for effect in effects):
            effected_nodes.append(node)

    for element in scene.elements:
        _walk(element)

    assert filtered_groups, "expected converted group filter metadata"
    group_meta = filtered_groups[0].metadata["filter_metadata"]["spec"]
    assert group_meta["stack_type"] == "specular_lighting_composite"

    assert effected_nodes, "expected child shapes to receive lighting effects"
    effect_xml = [
        getattr(effect, "drawingml", "")
        for node in effected_nodes
        for effect in (getattr(node, "effects", None) or [])
        if getattr(effect, "drawingml", "")
    ]
    assert any("<a:fillOverlay" in xml for xml in effect_xml)
    assert any("<a:glow" in xml for xml in effect_xml)
    assert any("<a:innerShdw" in xml for xml in effect_xml)


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
    scene = _convert_with_resvg(parse_result)

    paths = [element for element in scene.elements if isinstance(element, Path)]
    assert paths, "expected at least one path element in scene"
    path_metadata = paths[0].metadata if isinstance(paths[0].metadata, dict) else {}
    markers = path_metadata.get("markers", {})
    assert markers.get("end") == "arrow"
    marker_profiles = path_metadata.get("marker_profiles", {})
    assert marker_profiles.get("end", {}).get("type") == "triangle"
    assert marker_profiles.get("end", {}).get("source") == "geometry"


def test_path_with_circle_marker_adds_oval_profile() -> None:
    svg = (
        "<svg width='50' height='50' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <marker id='dot' markerWidth='1.5' markerHeight='1.5' orient='auto'>"
        "    <circle cx='0.75' cy='0.75' r='0.75'/>"
        "  </marker>"
        "</defs>"
        "<path d='M0 0 L10 0' stroke='#000000' marker-end='url(#dot)' fill='none'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)
    scene = _convert_with_resvg(parse_result)

    paths = [element for element in scene.elements if isinstance(element, Path)]
    assert paths, "expected at least one path element in scene"
    path_metadata = paths[0].metadata if isinstance(paths[0].metadata, dict) else {}
    marker_profiles = path_metadata.get("marker_profiles", {})
    assert marker_profiles.get("end", {}).get("type") == "oval"
    assert marker_profiles.get("end", {}).get("size") == "sm"


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
    scene = _convert_with_resvg(parse_result)

    rect = scene.elements[0]
    assert isinstance(rect, Rectangle)
    paint_policy = rect.metadata.get("policy", {}).get("paint", {})
    assert paint_policy.get("fill", {}).get("type") == "pattern"
    assert paint_policy["fill"]["id"] == "grid"
    analysis = rect.metadata.get("paint_analysis", {}).get("fill", {}).get("pattern")
    assert analysis is not None
    assert analysis["id"] == "grid"


def test_grouped_dot_pattern_stays_native() -> None:
    svg = (
        "<svg width='50' height='50' xmlns='http://www.w3.org/2000/svg' "
        "xmlns:sodipodi='http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd'>"
        "<defs>"
        "  <pattern id='dots' width='8' height='7' patternUnits='userSpaceOnUse' "
        "           patternTransform='translate(12,4)'>"
        "    <g transform='translate(-12,-4)'>"
        "      <rect width='8' height='7' style='fill:none;stroke:none'/>"
        "      <path sodipodi:type='arc' sodipodi:cx='14' sodipodi:cy='5' "
        "            sodipodi:rx='1' sodipodi:ry='1' style='fill:#000000;stroke:none' "
        "            d='M 15,5 A 1,1 0 1 1 15,4.99'/>"
        "      <path sodipodi:type='arc' sodipodi:cx='14' sodipodi:cy='5' "
        "            sodipodi:rx='1' sodipodi:ry='1' style='fill:#000000;stroke:none' "
        "            d='M 15,5 A 1,1 0 1 1 15,4.99' transform='translate(4,0)'/>"
        "      <path sodipodi:type='arc' sodipodi:cx='14' sodipodi:cy='5' "
        "            sodipodi:rx='1' sodipodi:ry='1' style='fill:#000000;stroke:none' "
        "            d='M 15,5 A 1,1 0 1 1 15,4.99' transform='translate(0,3)'/>"
        "      <path sodipodi:type='arc' sodipodi:cx='14' sodipodi:cy='5' "
        "            sodipodi:rx='1' sodipodi:ry='1' style='fill:#000000;stroke:none' "
        "            d='M 15,5 A 1,1 0 1 1 15,4.99' transform='translate(4,3)'/>"
        "    </g>"
        "  </pattern>"
        "</defs>"
        "<rect width='20' height='20' fill='url(#dots)'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)
    scene = _convert_with_resvg(parse_result)

    rect = scene.elements[0]
    assert isinstance(rect, Rectangle)
    assert isinstance(rect.fill, PatternPaint)
    paint_policy = rect.metadata.get("policy", {}).get("paint", {})
    assert paint_policy.get("fill", {}).get("type") == "pattern"
    assert paint_policy["fill"].get("suggest_fallback") is None
    assert (
        rect.metadata.get("policy", {}).get("geometry", {}).get("suggest_fallback")
        is None
    )
    assert rect.fill.background_opacity == 0.0
    analysis = rect.metadata.get("paint_analysis", {}).get("fill", {}).get("pattern")
    assert analysis is not None
    assert analysis["type"] == "dots"
    assert analysis["preset_candidate"] is not None


def test_grouped_dot_pattern_on_path_stays_native_with_tile() -> None:
    svg = (
        "<svg width='50' height='50' xmlns='http://www.w3.org/2000/svg' "
        "xmlns:sodipodi='http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd'>"
        "<defs>"
        "  <pattern id='dots' width='8' height='7' patternUnits='userSpaceOnUse' "
        "           patternTransform='translate(12,4)'>"
        "    <g transform='translate(-12,-4)'>"
        "      <rect width='8' height='7' style='fill:none;stroke:none'/>"
        "      <path sodipodi:type='arc' sodipodi:cx='14' sodipodi:cy='5' "
        "            sodipodi:rx='1' sodipodi:ry='1' style='fill:#000000;stroke:none' "
        "            d='M 15,5 A 1,1 0 1 1 15,4.99'/>"
        "      <path sodipodi:type='arc' sodipodi:cx='14' sodipodi:cy='5' "
        "            sodipodi:rx='1' sodipodi:ry='1' style='fill:#000000;stroke:none' "
        "            d='M 15,5 A 1,1 0 1 1 15,4.99' transform='translate(4,0)'/>"
        "      <path sodipodi:type='arc' sodipodi:cx='14' sodipodi:cy='5' "
        "            sodipodi:rx='1' sodipodi:ry='1' style='fill:#000000;stroke:none' "
        "            d='M 15,5 A 1,1 0 1 1 15,4.99' transform='translate(0,3)'/>"
        "      <path sodipodi:type='arc' sodipodi:cx='14' sodipodi:cy='5' "
        "            sodipodi:rx='1' sodipodi:ry='1' style='fill:#000000;stroke:none' "
        "            d='M 15,5 A 1,1 0 1 1 15,4.99' transform='translate(4,3)'/>"
        "    </g>"
        "  </pattern>"
        "</defs>"
        "<path d='M5,5 L45,5 L45,45 L5,45 Z' fill='url(#dots)'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)
    scene = _convert_with_resvg(parse_result)

    element = scene.elements[0]
    assert isinstance(element, Path)
    assert isinstance(element.fill, PatternPaint)
    assert element.fill.tile_image is not None
    assert element.fill.tile_image.startswith(b"\x89PNG")
    assert (
        element.metadata.get("paint_analysis", {})
        .get("fill", {})
        .get("pattern", {})
        .get("type")
        == "dots"
    )
    assert (
        element.metadata.get("policy", {}).get("geometry", {}).get(
            "suggest_fallback"
        )
        is None
    )


def test_gallardo_driver_side_pattern_paths_stay_native() -> None:
    scene = _convert_fixture_with_resvg("gallardo.svg")
    target_ids = {"path26665", "path27636", "path29576", "path23756"}
    seen: set[str] = set()

    for element in scene.elements:
        for node in _iter_scene_elements(element):
            ids = set(_element_ids(node))
            matches = ids & target_ids
            if not matches:
                continue
            seen.update(matches)
            assert not isinstance(node, Image)
            assert isinstance(node, Path)
            assert isinstance(node.fill, PatternPaint)
            assert node.fill.tile_image is not None
            assert node.fill.tile_image.startswith(b"\x89PNG")

    assert seen == target_ids


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
        metadata.setdefault("policy", {}).setdefault("geometry", {})[
            "render_mode"
        ] = "emf"
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

    scene = _convert_with_resvg(parse_result)

    assert calls.get("called") is True
    assert any(
        isinstance(elem, Image) and elem.format == "emf" for elem in scene.elements
    )


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

    scene = _convert_with_resvg(parse_result)

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

    scene = _convert_with_resvg(parse_result)

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

    scene = _convert_with_resvg(parse_result)

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

    scene = _convert_with_resvg(parse_result)

    clip_ref = next(
        path.clip
        for path in scene.elements
        if isinstance(path, Path) and path.clip is not None
    )
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

    scene = _convert_with_resvg(parse_result)

    clip_ref = next(
        path.clip
        for path in scene.elements
        if isinstance(path, Path) and path.clip is not None
    )
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

    scene = _convert_with_resvg(parse_result)

    clip_ref = next(
        path.clip
        for path in scene.elements
        if isinstance(path, Path) and path.clip is not None
    )
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

    scene = _convert_with_resvg(parse_result)

    clip_ref = next(
        path.clip
        for path in scene.elements
        if isinstance(path, Path) and path.clip is not None
    )
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

    scene = _convert_with_resvg(parse_result)

    clip_ref = next(
        path.clip
        for path in scene.elements
        if isinstance(path, Path) and path.clip is not None
    )
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
    scene = _convert_with_resvg(parse_result)

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
    scene = _convert_with_resvg(parse_result)

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
    assert any(
        isinstance(fill, SolidPaint) and fill.rgb.upper() == "00FF00"
        for fill in start_fills
    )
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
    scene = _convert_with_resvg(parse_result)

    marker_paths = [
        element
        for element in scene.elements
        if isinstance(element, Path)
        and element.metadata.get("marker_position") == "end"
    ]
    assert len(marker_paths) == 1
    marker_path = marker_paths[0]

    all_points = []
    for segment in marker_path.segments:
        if isinstance(segment, LineSegment):
            all_points.extend([segment.start, segment.end])
        elif isinstance(segment, BezierSegment):
            all_points.extend(
                [segment.start, segment.control1, segment.control2, segment.end]
            )

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
    scene = _convert_with_resvg(parse_result)

    marker_paths = [
        element
        for element in scene.elements
        if isinstance(element, Path)
        and element.metadata.get("marker_position") == "end"
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
            xs.extend(
                [segment.start.x, segment.control1.x, segment.control2.x, segment.end.x]
            )
            ys.extend(
                [segment.start.y, segment.control1.y, segment.control2.y, segment.end.y]
            )
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    assert pytest.approx(width, rel=1e-6) == pytest.approx(8.0)
    assert pytest.approx(height, rel=1e-6) == pytest.approx(4.0)


def test_marker_auto_orient_keeps_marker_origin_on_vertical_endpoint() -> None:
    svg = (
        "<svg width='40' height='40' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <marker id='tick' markerWidth='2' markerHeight='2' markerUnits='userSpaceOnUse' refX='0' refY='0' orient='auto'>"
        "    <path d='M0,0 L0,2' stroke='context-stroke' fill='none'/>"
        "  </marker>"
        "</defs>"
        "<path d='M0 0 L0 10' stroke='#000' stroke-width='1' marker-end='url(#tick)' fill='none'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)
    scene = _convert_with_resvg(parse_result)

    marker_path = next(
        element
        for element in scene.elements
        if isinstance(element, Path)
        and element.metadata.get("marker_position") == "end"
    )
    points = _path_points(marker_path)

    assert _has_point(points, 0.0, 10.0)
    assert _has_point(points, 2.0, 10.0)


def test_marker_auto_start_reverse_flips_start_marker_about_anchor() -> None:
    svg = (
        "<svg width='50' height='20' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <marker id='tick' markerWidth='2' markerHeight='2' markerUnits='userSpaceOnUse' refX='0' refY='0' orient='auto-start-reverse'>"
        "    <path d='M0,0 L2,0' stroke='context-stroke' fill='none'/>"
        "  </marker>"
        "</defs>"
        "<path d='M0 10 L20 10' stroke='#000' stroke-width='1' marker-start='url(#tick)' marker-end='url(#tick)' fill='none'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)
    scene = _convert_with_resvg(parse_result)

    start_marker = next(
        element
        for element in scene.elements
        if isinstance(element, Path)
        and element.metadata.get("marker_position") == "start"
    )
    end_marker = next(
        element
        for element in scene.elements
        if isinstance(element, Path)
        and element.metadata.get("marker_position") == "end"
    )

    start_points = _path_points(start_marker)
    end_points = _path_points(end_marker)

    assert _has_point(start_points, 0.0, 10.0)
    assert _has_point(start_points, -2.0, 10.0)
    assert _has_point(end_points, 20.0, 10.0)
    assert _has_point(end_points, 18.0, 10.0)


def test_marker_viewbox_ref_and_stroke_width_align_reference_point_to_endpoint() -> (
    None
):
    svg = (
        "<svg width='80' height='80' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <marker id='m' markerWidth='4' markerHeight='6' markerUnits='strokeWidth' refX='1' refY='2' orient='90' viewBox='0 0 2 3'>"
        "    <path d='M0,0 L2,0 L2,3 z' fill='context-stroke'/>"
        "  </marker>"
        "</defs>"
        "<path d='M10 20 L30 20' stroke='#000' stroke-width='5' marker-end='url(#m)' fill='none'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)
    scene = _convert_with_resvg(parse_result)

    marker_path = next(
        element
        for element in scene.elements
        if isinstance(element, Path)
        and element.metadata.get("marker_position") == "end"
    )
    points = _path_points(marker_path)

    assert _has_point(points, 50.0, 10.0)
    assert _has_point(points, 50.0, 30.0)
    assert _has_point(points, 20.0, 30.0)
    assert marker_path.metadata.get("marker_clip") == {
        "x": 0.0,
        "y": 0.0,
        "width": 20.0,
        "height": 30.0,
    }


def test_marker_child_transform_applies_in_marker_local_space() -> None:
    svg = (
        "<svg width='80' height='80' xmlns='http://www.w3.org/2000/svg'>"
        "<defs>"
        "  <marker id='m' markerWidth='4' markerHeight='4' markerUnits='userSpaceOnUse' refX='0' refY='0' orient='0'>"
        "    <path d='M0,0 L1,0' stroke='context-stroke' fill='none' transform='translate(3,4)'/>"
        "  </marker>"
        "</defs>"
        "<path d='M10 20 L30 20' stroke='#000' stroke-width='1' marker-end='url(#m)' fill='none'/>"
        "</svg>"
    )

    parse_result = _build_parse_result(svg)
    scene = _convert_with_resvg(parse_result)

    marker_path = next(
        element
        for element in scene.elements
        if isinstance(element, Path)
        and element.metadata.get("marker_position") == "end"
    )
    points = _path_points(marker_path)

    assert _has_point(points, 33.0, 24.0)
    assert _has_point(points, 34.0, 24.0)


def test_convert_path_produces_segments() -> None:
    parse_result = _build_parse_result(
        "<svg width='200' height='200' xmlns='http://www.w3.org/2000/svg'>"
        "<path d='M0 0 L10 0 L10 10 Z' fill='#00ff00'/>"
        "</svg>"
    )

    scene = _convert_with_resvg(parse_result)

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

    scene = _convert_with_resvg(parse_result)

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

    scene = _convert_with_resvg(parse_result)

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
    policy_context = PolicyContext(
        selections={"geometry": {"max_segments": 2, "simplify_paths": False}}
    )
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
        selections={
            "geometry": {
                "force_bitmap": True,
                "max_bitmap_area": 2500,
                "max_bitmap_side": 1000,
            }
        }
    )
    converter = IRConverter(services=services, policy_context=policy_context)

    scene = converter.convert(parse_result)

    assert isinstance(scene.elements[0], Path)
    geometry_meta = scene.elements[0].metadata.get("policy", {}).get("geometry", {})
    assert geometry_meta.get("bitmap_suppressed") == "max_area"
    assert geometry_meta.get("bitmap_limit_area") == 2500
