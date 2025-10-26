"""Tests for the simplified SVG parser."""

from svg2ooxml.parser import ParseResult, SVGParser
from svg2ooxml.parser.svg_parser import ParserConfig


def test_parse_returns_success_with_valid_svg() -> None:
    parser = SVGParser()
    svg = "<svg width='10' height='10'><rect width='10' height='10'/></svg>"

    result = parser.parse(svg)

    assert isinstance(result, ParseResult)
    assert result.success is True
    assert result.svg_root.tag.endswith("svg")
    assert result.element_count == 2
    assert result.namespaces[None] == "http://www.w3.org/2000/svg"
    assert result.has_external_references is False
    assert getattr(result, "clip_paths", None) in (None, {})
    assert getattr(result, "clip_geometry", None) in (None, {})
    assert result.masks == {}
    assert result.symbols == {}
    assert result.filters == {}
    assert result.services is not None
    assert result.services.resolve('clip_paths') is None
    assert result.root_style["font_family"] == "Arial"
    assert result.normalization_changes is not None
    assert result.width_px == 10.0
    assert result.height_px == 10.0
    assert result.viewbox_scale is None
    assert result.root_color is None
    assert result.processing_time_ms >= 0.0
    assert result.normalization_applied is True
    assert result.metadata["preparse"]["added_xml_declaration"] is True
    assert result.normalization_changes["preparse"]["added_xml_declaration"] is True


def test_parse_rejects_non_svg_root() -> None:
    parser = SVGParser()

    result = parser.parse("<root></root>")

    assert result.success is False
    assert result.error == "Content does not appear to be SVG"
    assert result.processing_time_ms >= 0.0
    assert result.metadata["preparse"]["error"] == "missing_svg_tag"


def test_parse_strips_whitespace_when_configured() -> None:
    parser = SVGParser(ParserConfig(strip_whitespace=True))
    svg = "<svg width='10' height='10'>  <text> hello </text> </svg>"

    result = parser.parse(svg)

    assert result.success is True
    text_node = next(
        result.svg_root.iterfind(".//{http://www.w3.org/2000/svg}text"),
        None,
    )
    assert text_node.text == "hello"
    assert result.namespaces[None] == "http://www.w3.org/2000/svg"
    assert getattr(result, "clip_paths", None) in (None, {})
    assert getattr(result, "clip_geometry", None) in (None, {})
    assert result.masks == {}
    assert result.symbols == {}
    assert result.filters == {}
    assert result.services is not None
    assert result.services.resolve('clip_paths') is None
    assert result.root_style["font_family"] == "Arial"
    assert result.normalization_changes is not None
    assert result.width_px == 10.0
    assert result.height_px == 10.0
    assert result.viewbox_scale is None
    assert result.root_color is None


def test_parse_warns_when_dimensions_missing() -> None:
    parser = SVGParser()
    svg = "<svg><rect/></svg>"

    result = parser.parse(svg)

    assert result.success is True
    assert result.error == "SVG element missing width/height or viewBox."
    assert result.namespaces[None] == "http://www.w3.org/2000/svg"
    assert getattr(result, "clip_paths", None) in (None, {})
    assert getattr(result, "clip_geometry", None) in (None, {})
    assert result.masks == {}
    assert result.symbols == {}
    assert result.filters == {}
    assert result.services is not None
    assert result.services.resolve('clip_paths') is None
    assert result.root_style["font_family"] == "Arial"
    assert result.normalization_changes is not None
    assert result.width_px is None
    assert result.height_px is None
    assert result.viewbox_scale is None
    assert result.root_color is None


def test_parse_extracts_root_color_when_present() -> None:
    parser = SVGParser()
    svg = "<svg width='10' height='10' color='#123456'><rect/></svg>"

    result = parser.parse(svg)

    assert result.success is True
    assert result.root_style["fill"] == "#000000"
    assert result.root_color == (0x12 / 255.0, 0x34 / 255.0, 0x56 / 255.0, 1.0)
    assert result.width_px == 10.0
    assert result.height_px == 10.0


def test_parse_computes_viewbox_scale_when_available() -> None:
    parser = SVGParser()
    svg = "<svg width='200' height='100' viewBox='0 0 100 50'><rect/></svg>"

    result = parser.parse(svg)

    assert result.success is True
    assert result.viewbox_scale == (2.0, 2.0)


def test_parse_emits_metrics(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_record_metric(name: str, payload: dict[str, object], **kwargs):
        calls.append({"name": name, "payload": payload, "kwargs": kwargs})
        return {"name": name, "payload": payload, "kwargs": kwargs}

    monkeypatch.setattr(
        "svg2ooxml.parser.svg_parser.record_metric",
        fake_record_metric,
    )

    parser = SVGParser()
    svg = "<svg width='10' height='10'><rect width='10' height='10'/></svg>"

    parser.parse(svg)

    assert calls, "Expected metrics to be recorded"
    entry = calls[-1]
    assert entry["name"] == "parser.run"
    payload = entry["payload"]
    assert payload["success"] is True
    assert payload["element_count"] == 2
    assert payload["preparse"]["added_xml_declaration"] is True


def test_parse_no_longer_registers_clip_geometry_service() -> None:
    parser = SVGParser()
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>"
        "<defs><clipPath id='clipA'><rect width='2' height='2'/></clipPath></defs>"
        "<rect clip-path='url(#clipA)' width='5' height='5'/></svg>"
    )

    result = parser.parse(svg)

    assert getattr(result, "clip_paths", None) in (None, {})
    assert getattr(result, "clip_geometry", None) in (None, {})
    assert result.services.resolve('clip_geometry') is None
