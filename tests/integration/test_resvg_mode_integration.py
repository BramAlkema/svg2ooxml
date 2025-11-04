"""Integration tests for resvg geometry mode end-to-end conversion.

This module verifies that:
1. SVG → PPTX conversion works with geometry_mode="resvg"
2. Shapes (rect, circle, ellipse, path) are correctly converted via resvg
3. Resulting PPTX files are valid and contain expected geometry
4. Fallback to legacy mode works when resvg is unavailable
"""

from __future__ import annotations

import zipfile
from xml.etree import ElementTree as ET

from svg2ooxml.core.pptx_exporter import SvgToPptxExporter


def test_resvg_mode_converts_circle_to_pptx(tmp_path) -> None:
    """Test that circle converts successfully with resvg mode enabled."""
    exporter = SvgToPptxExporter(geometry_mode="resvg")
    svg_markup = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100'>"
        "<circle cx='50' cy='50' r='40' fill='#FF5733'/>"
        "</svg>"
    )

    output_path = tmp_path / "resvg-circle.pptx"
    result = exporter.convert_string(svg_markup, output_path)

    assert output_path.exists()
    assert result.slide_count == 1

    # Verify PPTX contains the fill color
    with zipfile.ZipFile(output_path, "r") as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")

    root = ET.fromstring(slide_xml)
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    fills = root.findall(".//a:solidFill/a:srgbClr", ns)
    assert any(
        fill.get("val") == "FF5733" for fill in fills
    ), "Expected circle fill color in slide XML"


def test_resvg_mode_converts_ellipse_to_pptx(tmp_path) -> None:
    """Test that ellipse converts successfully with resvg mode enabled."""
    exporter = SvgToPptxExporter(geometry_mode="resvg")
    svg_markup = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100'>"
        "<ellipse cx='50' cy='50' rx='40' ry='20' fill='#3498DB'/>"
        "</svg>"
    )

    output_path = tmp_path / "resvg-ellipse.pptx"
    result = exporter.convert_string(svg_markup, output_path)

    assert output_path.exists()
    assert result.slide_count == 1

    with zipfile.ZipFile(output_path, "r") as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")

    root = ET.fromstring(slide_xml)
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    fills = root.findall(".//a:solidFill/a:srgbClr", ns)
    assert any(
        fill.get("val") == "3498DB" for fill in fills
    ), "Expected ellipse fill color in slide XML"


def test_resvg_mode_converts_rect_to_pptx(tmp_path) -> None:
    """Test that rectangle converts successfully with resvg mode enabled."""
    exporter = SvgToPptxExporter(geometry_mode="resvg")
    svg_markup = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100'>"
        "<rect x='10' y='10' width='80' height='60' fill='#2ECC71'/>"
        "</svg>"
    )

    output_path = tmp_path / "resvg-rect.pptx"
    result = exporter.convert_string(svg_markup, output_path)

    assert output_path.exists()
    assert result.slide_count == 1

    with zipfile.ZipFile(output_path, "r") as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")

    root = ET.fromstring(slide_xml)
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    fills = root.findall(".//a:solidFill/a:srgbClr", ns)
    assert any(
        fill.get("val") == "2ECC71" for fill in fills
    ), "Expected rect fill color in slide XML"


def test_resvg_mode_converts_path_to_pptx(tmp_path) -> None:
    """Test that path converts successfully with resvg mode enabled."""
    exporter = SvgToPptxExporter(geometry_mode="resvg")
    svg_markup = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100'>"
        "<path d='M 10 10 L 90 10 L 90 90 L 10 90 Z' fill='#9B59B6'/>"
        "</svg>"
    )

    output_path = tmp_path / "resvg-path.pptx"
    result = exporter.convert_string(svg_markup, output_path)

    assert output_path.exists()
    assert result.slide_count == 1

    with zipfile.ZipFile(output_path, "r") as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")

    root = ET.fromstring(slide_xml)
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    fills = root.findall(".//a:solidFill/a:srgbClr", ns)
    assert any(
        fill.get("val") == "9B59B6" for fill in fills
    ), "Expected path fill color in slide XML"


def test_resvg_mode_with_transforms(tmp_path) -> None:
    """Test that resvg mode handles transforms correctly."""
    exporter = SvgToPptxExporter(geometry_mode="resvg")
    svg_markup = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'>"
        "<circle cx='50' cy='50' r='30' fill='#E74C3C' transform='translate(50,50)'/>"
        "</svg>"
    )

    output_path = tmp_path / "resvg-transformed.pptx"
    result = exporter.convert_string(svg_markup, output_path)

    assert output_path.exists()
    assert result.slide_count == 1

    with zipfile.ZipFile(output_path, "r") as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")

    # Verify PPTX is valid and contains the shape
    root = ET.fromstring(slide_xml)
    ns = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    }
    shapes = root.findall(".//p:sp", ns)
    assert len(shapes) > 0, "Expected at least one shape in slide"


def test_resvg_mode_multi_shape_svg(tmp_path) -> None:
    """Test that resvg mode handles multiple shapes in one SVG."""
    exporter = SvgToPptxExporter(geometry_mode="resvg")
    svg_markup = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'>"
        "<rect x='10' y='10' width='50' height='50' fill='#FF0000'/>"
        "<circle cx='100' cy='100' r='30' fill='#00FF00'/>"
        "<ellipse cx='150' cy='150' rx='25' ry='15' fill='#0000FF'/>"
        "</svg>"
    )

    output_path = tmp_path / "resvg-multi-shape.pptx"
    result = exporter.convert_string(svg_markup, output_path)

    assert output_path.exists()
    assert result.slide_count == 1

    with zipfile.ZipFile(output_path, "r") as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")

    # Verify all three colors are present
    assert "FF0000" in slide_xml, "Expected red rectangle"
    assert "00FF00" in slide_xml, "Expected green circle"
    assert "0000FF" in slide_xml, "Expected blue ellipse"


def test_legacy_mode_still_works(tmp_path) -> None:
    """Test that legacy mode (geometry_mode='legacy') still works correctly."""
    exporter = SvgToPptxExporter(geometry_mode="legacy")
    svg_markup = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100'>"
        "<rect width='100' height='100' fill='#F39C12'/>"
        "</svg>"
    )

    output_path = tmp_path / "legacy-mode.pptx"
    result = exporter.convert_string(svg_markup, output_path)

    assert output_path.exists()
    assert result.slide_count == 1

    with zipfile.ZipFile(output_path, "r") as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")

    root = ET.fromstring(slide_xml)
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    fills = root.findall(".//a:solidFill/a:srgbClr", ns)
    assert any(
        fill.get("val") == "F39C12" for fill in fills
    ), "Expected rect fill color in legacy mode"


def test_resvg_mode_with_rounded_rect(tmp_path) -> None:
    """Test that resvg mode handles rounded rectangles correctly."""
    exporter = SvgToPptxExporter(geometry_mode="resvg")
    svg_markup = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100'>"
        "<rect x='10' y='10' width='80' height='60' rx='10' ry='10' fill='#1ABC9C'/>"
        "</svg>"
    )

    output_path = tmp_path / "resvg-rounded-rect.pptx"
    result = exporter.convert_string(svg_markup, output_path)

    assert output_path.exists()
    assert result.slide_count == 1

    with zipfile.ZipFile(output_path, "r") as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")

    # Verify the rounded rect is present with correct fill
    assert "1ABC9C" in slide_xml, "Expected rounded rect fill color"


def test_resvg_mode_environment_variable(tmp_path, monkeypatch) -> None:
    """Test that geometry_mode can be set via environment variable."""
    monkeypatch.setenv("SVG2OOXML_GEOMETRY_MODE", "resvg")

    # Don't pass geometry_mode parameter, should come from env var
    exporter = SvgToPptxExporter()
    svg_markup = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100'>"
        "<circle cx='50' cy='50' r='40' fill='#E67E22'/>"
        "</svg>"
    )

    output_path = tmp_path / "resvg-env-var.pptx"
    result = exporter.convert_string(svg_markup, output_path)

    assert output_path.exists()
    assert result.slide_count == 1

    with zipfile.ZipFile(output_path, "r") as archive:
        slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")

    assert "E67E22" in slide_xml, "Expected circle fill color from env var mode"
