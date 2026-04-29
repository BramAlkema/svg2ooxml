"""End-to-end checks around the SVG to PPTX exporter."""

from __future__ import annotations

import json
import zipfile

import pytest
from lxml import etree as ET

from svg2ooxml.core.pptx_exporter import (
    SvgConversionError,
    SvgPageSource,
    SvgToPptxExporter,
)
from svg2ooxml.io.pptx_docprops import CUSTOM_PROPERTIES_PART, CUSTOM_TRACE_PROPERTY


def test_convert_string_produces_slide_with_expected_fill(tmp_path) -> None:
    exporter = SvgToPptxExporter()
    svg_markup = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>"
        "<rect width='10' height='10' fill='#336699'/>"
        "</svg>"
    )

    output_path = tmp_path / "single-slide.pptx"
    result = exporter.convert_string(svg_markup, output_path)

    assert output_path.exists()
    assert result.slide_count == 1
    stage_totals = result.trace_report.get("stage_totals", {})
    assert stage_totals.get("parser:normalization") == 1
    assert isinstance(result.trace_report.get("resvg_metrics", {}), dict)

    with zipfile.ZipFile(output_path, "r") as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")

    root = ET.fromstring(slide_xml.encode())
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    fills = root.findall(".//a:solidFill/a:srgbClr", ns)
    assert any(
        fill.get("val") == "336699" for fill in fills
    ), "Expected rectangle fill colour in slide XML"


def test_convert_string_embeds_trace_docprops_only_when_requested(tmp_path) -> None:
    exporter = SvgToPptxExporter()
    svg_markup = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>"
        "<rect width='10' height='10' fill='#336699'/>"
        "</svg>"
    )

    default_path = tmp_path / "default.pptx"
    exporter.convert_string(svg_markup, default_path)
    with zipfile.ZipFile(default_path, "r") as archive:
        assert CUSTOM_PROPERTIES_PART not in set(archive.namelist())

    embedded_path = tmp_path / "embedded.pptx"
    exporter.convert_string(svg_markup, embedded_path, embed_trace_docprops=True)
    with zipfile.ZipFile(embedded_path, "r") as archive:
        custom_xml = archive.read(CUSTOM_PROPERTIES_PART)

    payload = _trace_payload_from_custom_xml(custom_xml)
    assert payload["stage_totals"]["parser:normalization"] == 1


@pytest.mark.parametrize("parallel", [False, True])
def test_convert_pages_creates_multi_slide_package(tmp_path, parallel: bool) -> None:
    exporter = SvgToPptxExporter()
    slide_one = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>"
        "<rect width='10' height='10' fill='#ff0000'/>"
        "</svg>"
    )
    slide_two = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>"
        "<circle cx='5' cy='5' r='5' fill='#00ff00'/>"
        "</svg>"
    )
    pages = [
        SvgPageSource(svg_text=slide_one, title="First", name="first"),
        SvgPageSource(svg_text=slide_two, title="Second", name="second"),
    ]

    suffix = "parallel" if parallel else "serial"
    output_path = tmp_path / f"multi-slide-{suffix}.pptx"
    multi_result = exporter.convert_pages(pages, output_path, parallel=parallel)

    assert output_path.exists()
    assert multi_result.slide_count == len(pages)
    assert len(multi_result.page_results) == len(pages)

    aggregated_totals = multi_result.aggregated_trace_report.get("stage_totals", {})
    assert aggregated_totals.get("parser:normalization") == len(pages)
    assert isinstance(
        multi_result.aggregated_trace_report.get("resvg_metrics", {}), dict
    )

    packaging_totals = multi_result.packaging_report.get("stage_totals", {})
    assert packaging_totals.get("packaging:slide_xml_written") == len(pages)

    assert all(
        page.trace_report.get("stage_totals", {}).get("parser:normalization") == 1
        for page in multi_result.page_results
    )

    with zipfile.ZipFile(output_path, "r") as archive:
        names = set(archive.namelist())
        expected_slides = {
            f"ppt/slides/slide{index}.xml" for index in range(1, len(pages) + 1)
        }
        assert expected_slides.issubset(names)

        slide1_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        slide2_xml = archive.read("ppt/slides/slide2.xml").decode("utf-8")
        assert "FF0000" in slide1_xml
        assert "00FF00" in slide2_xml


def test_parallel_convert_pages_rejects_custom_render_components(tmp_path) -> None:
    exporter = SvgToPptxExporter(parser=object())  # type: ignore[arg-type]
    pages = [
        SvgPageSource(
            svg_text="<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'/>"
        )
    ]

    with pytest.raises(SvgConversionError, match="custom render components: parser"):
        exporter.convert_pages(pages, tmp_path / "custom-parallel.pptx", parallel=True)


def _trace_payload_from_custom_xml(custom_xml: bytes) -> dict[str, object]:
    root = ET.fromstring(custom_xml)
    ns = {
        "cp": "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties",
        "vt": "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes",
    }
    prop = root.find(f".//cp:property[@name='{CUSTOM_TRACE_PROPERTY}']", ns)
    assert prop is not None
    value = prop.find("vt:lpwstr", ns)
    assert value is not None and value.text
    payload = json.loads(value.text)
    assert isinstance(payload, dict)
    return payload
