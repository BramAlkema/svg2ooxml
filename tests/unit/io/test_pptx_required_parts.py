"""Tests for required PPTX parts (presProps, viewProps, tableStyles)."""

import tempfile
import zipfile
from pathlib import Path

from lxml import etree as ET

from svg2ooxml.core.pptx_exporter import SvgPageSource, SvgToPptxExporter
from svg2ooxml.drawingml.generator import px_to_emu
from svg2ooxml.drawingml.writer import DEFAULT_SLIDE_SIZE


def test_pptx_includes_required_parts():
    """Verify that generated PPTX includes all required parts per ECMA-376."""
    # Simple test SVG
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
        <rect x="10" y="10" width="80" height="80" fill="blue"/>
    </svg>"""

    # Generate PPTX
    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
        output_path = Path(f.name)

    try:
        exporter = SvgToPptxExporter()
        exporter.convert_string(svg, str(output_path))

        # Verify files exist in PPTX
        with zipfile.ZipFile(output_path, "r") as z:
            files = set(z.namelist())

            # Check required XML files exist
            assert "ppt/presProps.xml" in files, "Missing presProps.xml"
            assert "ppt/viewProps.xml" in files, "Missing viewProps.xml"
            assert "ppt/tableStyles.xml" in files, "Missing tableStyles.xml"

            # Verify presProps.xml content
            pres_props = z.read("ppt/presProps.xml").decode("utf-8")
            assert "presentationPr" in pres_props
            assert 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"' in pres_props

            # Verify viewProps.xml content
            view_props = z.read("ppt/viewProps.xml").decode("utf-8")
            assert "viewPr" in view_props
            assert "normalViewPr" in view_props

            # Verify tableStyles.xml content
            table_styles = z.read("ppt/tableStyles.xml").decode("utf-8")
            assert "tblStyleLst" in table_styles
            assert 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"' in table_styles

    finally:
        if output_path.exists():
            output_path.unlink()


def test_content_types_declares_required_parts():
    """Verify that [Content_Types].xml includes declarations for required parts."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
        <circle cx="50" cy="50" r="40" fill="red"/>
    </svg>"""

    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
        output_path = Path(f.name)

    try:
        exporter = SvgToPptxExporter()
        exporter.convert_string(svg, str(output_path))

        with zipfile.ZipFile(output_path, "r") as z:
            content_types = z.read("[Content_Types].xml").decode("utf-8")

            # Check Override elements for required parts
            assert "/ppt/presProps.xml" in content_types
            assert "presentationml.presProps+xml" in content_types

            assert "/ppt/viewProps.xml" in content_types
            assert "presentationml.viewProps+xml" in content_types

            assert "/ppt/tableStyles.xml" in content_types
            assert "presentationml.tableStyles+xml" in content_types

    finally:
        if output_path.exists():
            output_path.unlink()


def test_presentation_rels_includes_required_relationships():
    """Verify that presentation.xml.rels includes relationships to required parts."""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
        <path d="M 10,10 L 90,90" stroke="black"/>
    </svg>"""

    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
        output_path = Path(f.name)

    try:
        exporter = SvgToPptxExporter()
        exporter.convert_string(svg, str(output_path))

        with zipfile.ZipFile(output_path, "r") as z:
            rels = z.read("ppt/_rels/presentation.xml.rels").decode("utf-8")

            # Check Relationship elements for required parts
            assert "presProps.xml" in rels
            assert "relationships/presProps" in rels

            assert "viewProps.xml" in rels
            assert "relationships/viewProps" in rels

            assert "tableStyles.xml" in rels
            assert "relationships/tableStyles" in rels

    finally:
        if output_path.exists():
            output_path.unlink()


def _read_slide_size(pptx_path: Path) -> tuple[int, int]:
    with zipfile.ZipFile(pptx_path, "r") as archive:
        presentation_xml = archive.read("ppt/presentation.xml")
    root = ET.fromstring(presentation_xml)
    ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
    sld_sz = root.find("p:sldSz", ns)
    assert sld_sz is not None, "presentation.xml missing <p:sldSz> element"
    return int(sld_sz.get("cx")), int(sld_sz.get("cy"))


def test_slide_size_mode_same_matches_svg_dimensions():
    svg = """<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"320\" height=\"180\">
        <rect width=\"320\" height=\"180\" fill=\"#4285F4\"/>
    </svg>"""

    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
        output_path = Path(f.name)

    try:
        exporter = SvgToPptxExporter(slide_size_mode="same")
        exporter.convert_string(svg, output_path)

        width_emu, height_emu = _read_slide_size(output_path)
        assert width_emu == px_to_emu(320)
        assert height_emu == px_to_emu(180)
    finally:
        if output_path.exists():
            output_path.unlink()


def test_slide_size_mode_multipage_uses_largest_page():
    svg_small = """<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"200\" height=\"150\">
        <rect width=\"200\" height=\"150\" fill=\"#FF0000\"/>
    </svg>"""
    svg_large = """<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1200\" height=\"800\">
        <rect width=\"1200\" height=\"800\" fill=\"#00FF00\"/>
    </svg>"""

    pages = [
        SvgPageSource(svg_text=svg_small, title="Small"),
        SvgPageSource(svg_text=svg_large, title="Large"),
    ]

    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
        output_path = Path(f.name)

    try:
        exporter = SvgToPptxExporter(slide_size_mode="multipage")
        exporter.convert_pages(pages, output_path)

        width_emu, height_emu = _read_slide_size(output_path)
        expected_width = max(DEFAULT_SLIDE_SIZE[0], px_to_emu(1200))
        expected_height = max(DEFAULT_SLIDE_SIZE[1], px_to_emu(800))
        assert width_emu == expected_width
        assert height_emu == expected_height
    finally:
        if output_path.exists():
            output_path.unlink()


def test_font_content_type_is_powerpoint_compliant():
    """Verify font content type uses PowerPoint-compliant 'application/x-fontdata'.

    Per ECMA-376, PowerPoint expects 'application/x-fontdata' for TTF/OTF fonts.
    Using 'application/x-font-ttf' causes PowerPoint to strip all fonts during repair.
    """
    from svg2ooxml.io.pptx_assembly import content_type_for_extension as _content_type_for_extension

    # Test TTF font
    ttf_type = _content_type_for_extension("ttf")
    assert ttf_type == "application/x-fontdata", (
        f"TTF content type should be 'application/x-fontdata' (PowerPoint-compliant), "
        f"not '{ttf_type}'"
    )

    # Test OTF font
    otf_type = _content_type_for_extension("otf")
    assert otf_type == "application/x-fontdata", (
        f"OTF content type should be 'application/x-fontdata' (PowerPoint-compliant), "
        f"not '{otf_type}'"
    )

    # Test that old non-compliant types are NOT used
    assert ttf_type != "application/x-font-ttf", "Should not use non-compliant x-font-ttf"
    assert otf_type != "application/x-font-otf", "Should not use non-compliant x-font-otf"


def test_powerpoint_validation_compliance():
    """Integration test: Generated PPTX should be PowerPoint-compliant.

    This test verifies that all required ECMA-376 parts are present,
    which should prevent PowerPoint from requiring file repair.
    """
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">
        <rect x="20" y="20" width="160" height="160" fill="green" stroke="blue" stroke-width="5"/>
        <text x="100" y="110" text-anchor="middle" fill="white" font-size="24">Test</text>
    </svg>"""

    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
        output_path = Path(f.name)

    try:
        exporter = SvgToPptxExporter()
        exporter.convert_string(svg, str(output_path))

        # Comprehensive validation
        with zipfile.ZipFile(output_path, "r") as z:
            files = set(z.namelist())

            # Required files per ECMA-376
            required_files = [
                "ppt/presProps.xml",
                "ppt/viewProps.xml",
                "ppt/tableStyles.xml",
                "ppt/presentation.xml",
                "[Content_Types].xml",
                "ppt/_rels/presentation.xml.rels",
            ]

            missing = [f for f in required_files if f not in files]
            assert not missing, f"Missing required files: {missing}"

            # Verify proper XML structure
            for required_file in ["ppt/presProps.xml", "ppt/viewProps.xml", "ppt/tableStyles.xml"]:
                content = z.read(required_file).decode("utf-8")
                assert content.startswith('<?xml version="1.0"'), f"{required_file} missing XML declaration"
                assert "xmlns" in content, f"{required_file} missing namespace declaration"

    finally:
        if output_path.exists():
            output_path.unlink()


def test_hyperlink_format_does_not_use_invalid_ppaction():
    """Verify hyperlinks don't use invalid ppaction:// formats that PowerPoint strips.

    Per ECMA-376, ppaction://hlinkshowjump only supports 'jump' parameter with values:
    nextslide, previousslide, firstslide, lastslide, endshow.

    The 'bookmark' and 'show' parameters are NOT part of the specification and cause
    PowerPoint to strip hyperlinks during repair.
    """
    # SVG with a fragment identifier link (href="#target")
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"
                  xmlns:xlink="http://www.w3.org/1999/xlink">
        <rect id="link-rect" x="20" y="20" width="80" height="80" fill="blue">
            <a xlink:href="#target">
                <title>Link to target</title>
            </a>
        </rect>
        <rect id="target" x="120" y="120" width="60" height="60" fill="red"/>
    </svg>"""

    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
        output_path = Path(f.name)

    try:
        exporter = SvgToPptxExporter()
        exporter.convert_string(svg, str(output_path))

        # Check that slide XML doesn't contain invalid ppaction:// URLs
        with zipfile.ZipFile(output_path, "r") as z:
            slide_files = [f for f in z.namelist() if f.startswith("ppt/slides/slide") and f.endswith(".xml")]

            for slide_file in slide_files:
                content = z.read(slide_file).decode("utf-8")

                # Should NOT contain invalid ppaction:// formats
                assert "ppaction://hlinkshowjump?bookmark=" not in content, (
                    f"{slide_file} contains invalid ppaction:// URL with bookmark parameter"
                )
                assert "ppaction://hlinkshowjump?show=" not in content, (
                    f"{slide_file} contains invalid ppaction:// URL with show parameter"
                )

                # If there are any ppaction:// URLs, they should only use valid jump parameter
                if "ppaction://hlinkshowjump" in content:
                    assert "ppaction://hlinkshowjump?jump=" in content, (
                        f"{slide_file} has ppaction:// URL without valid jump parameter"
                    )

    finally:
        if output_path.exists():
            output_path.unlink()
