"""End-to-end checks around the SVG to PPTX exporter."""

from __future__ import annotations

import zipfile
from xml.etree import ElementTree as ET

from svg2ooxml.core.pptx_exporter import SvgPageSource, SvgToPptxExporter

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

    root = ET.fromstring(slide_xml)
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    fills = root.findall(".//a:solidFill/a:srgbClr", ns)
    assert any(fill.get("val") == "336699" for fill in fills), "Expected rectangle fill colour in slide XML"


def test_convert_pages_creates_multi_slide_package(tmp_path) -> None:
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

    output_path = tmp_path / "multi-slide.pptx"
    multi_result = exporter.convert_pages(pages, output_path)

    assert output_path.exists()
    assert multi_result.slide_count == len(pages)
    assert len(multi_result.page_results) == len(pages)

    aggregated_totals = multi_result.aggregated_trace_report.get("stage_totals", {})
    assert aggregated_totals.get("parser:normalization") == len(pages)
    assert isinstance(multi_result.aggregated_trace_report.get("resvg_metrics", {}), dict)

    packaging_totals = multi_result.packaging_report.get("stage_totals", {})
    assert packaging_totals.get("packaging:slide_xml_written") == len(pages)

    assert all(
        page.trace_report.get("stage_totals", {}).get("parser:normalization") == 1
        for page in multi_result.page_results
    )

    with zipfile.ZipFile(output_path, "r") as archive:
        names = set(archive.namelist())
        expected_slides = {f"ppt/slides/slide{index}.xml" for index in range(1, len(pages) + 1)}
        assert expected_slides.issubset(names)

        slide1_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
        slide2_xml = archive.read("ppt/slides/slide2.xml").decode("utf-8")
        assert "FF0000" in slide1_xml
        assert "00FF00" in slide2_xml
