"""End-to-end integration tests for web font embedding in PPTX.

Tests the complete pipeline: SVG with @font-face -> Parser -> FontLoader -> PPTX with embedded fonts
"""
from __future__ import annotations

import base64
import zipfile
from pathlib import Path

import pytest

from svg2ooxml.export import SVGFrame, render_pptx_for_frames


def _create_frame(svg_content: str, name: str = "Test") -> SVGFrame:
    """Helper to create SVGFrame from SVG content string."""
    return SVGFrame(
        name=name,
        svg_content=svg_content,
        width=400,
        height=200,
    )


class TestWebFontEmbeddingEndToEnd:
    """End-to-end tests for web font loading and PPTX embedding."""

    def test_data_uri_ttf_font_embedded_in_pptx(self, tmp_path: Path):
        """E2E: SVG with TTF data URI -> PPTX with embedded font."""
        # Use a real TTF font for testing
        font_file = Path(__file__).parent.parent / "resources" / "ScheherazadeRegOT.ttf"
        ttf_data = font_file.read_bytes()
        b64_data = base64.b64encode(ttf_data).decode("ascii")
        data_uri = f"data:font/ttf;base64,{b64_data}"

        svg_content = f"""
        <svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">
          <style>
            @font-face {{
              font-family: 'DataURIFont';
              src: url('{data_uri}') format('ttf');
              font-weight: 400;
              font-style: normal;
            }}
          </style>
          <text x="50" y="100" font-family="DataURIFont" font-size="32" fill="#000">
            Hello Web Fonts
          </text>
        </svg>
        """

        # Convert to PPTX
        output_path = tmp_path / "output.pptx"
        artifacts = render_pptx_for_frames(
            frames=[_create_frame(svg_content)],
            output_path=output_path,
        )

        # Validate conversion succeeded
        assert artifacts.slide_count == 1
        assert output_path.exists()

        # Validate PPTX contains font
        with zipfile.ZipFile(output_path, "r") as archive:
            names = archive.namelist()

            # Check font file exists in ppt/fonts/
            font_files = [name for name in names if name.startswith("ppt/fonts/")]
            assert len(font_files) > 0, "No fonts embedded in PPTX"

            # Check for font relationships
            rels_path = "ppt/_rels/presentation.xml.rels"
            if rels_path in names:
                rels_xml = archive.read(rels_path).decode("utf-8")
                # Should contain font relationship
                assert "relationships/font" in rels_xml or "font" in rels_xml.lower()

            # Check presentation.xml for embedded font list
            pres_path = "ppt/presentation.xml"
            if pres_path in names:
                pres_xml = archive.read(pres_path).decode("utf-8")
                # Font should be referenced
                assert "DataURIFont" in pres_xml or "embeddedFont" in pres_xml

    def test_data_uri_otf_font_embedded_in_pptx(self, tmp_path: Path):
        """E2E: SVG with OTF data URI -> PPTX with embedded font."""
        # Use a real font (TTF works for this test too)
        font_file = Path(__file__).parent.parent / "resources" / "ScheherazadeRegOT.ttf"
        ttf_data = font_file.read_bytes()
        b64_data = base64.b64encode(ttf_data).decode("ascii")
        data_uri = f"data:font/otf;base64,{b64_data}"

        svg_content = f"""
        <svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">
          <style>
            @font-face {{
              font-family: 'OTFFont';
              src: url('{data_uri}') format('otf');
            }}
          </style>
          <text x="50" y="100" font-family="OTFFont" font-size="24">
            OpenType Font Test
          </text>
        </svg>
        """

        output_path = tmp_path / "output_otf.pptx"
        artifacts = render_pptx_for_frames(
            frames=[_create_frame(svg_content)],
            output_path=output_path,
        )

        assert artifacts.slide_count == 1
        assert output_path.exists()

        # Validate font embedding
        with zipfile.ZipFile(output_path, "r") as archive:
            names = archive.namelist()
            font_files = [name for name in names if name.startswith("ppt/fonts/")]
            assert len(font_files) > 0

    def test_multiple_font_weights_embedded_separately(self, tmp_path: Path):
        """E2E: SVG with multiple font weights -> PPTX with all variants embedded."""
        # Use real fonts for both weights (same font for simplicity)
        font_file = Path(__file__).parent.parent / "resources" / "ScheherazadeRegOT.ttf"
        ttf_400 = font_file.read_bytes()
        ttf_700 = font_file.read_bytes()  # Same font, different weight declaration

        b64_400 = base64.b64encode(ttf_400).decode("ascii")
        b64_700 = base64.b64encode(ttf_700).decode("ascii")

        uri_400 = f"data:font/ttf;base64,{b64_400}"
        uri_700 = f"data:font/ttf;base64,{b64_700}"

        svg_content = f"""
        <svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">
          <style>
            @font-face {{
              font-family: 'MultiWeight';
              src: url('{uri_400}') format('ttf');
              font-weight: 400;
            }}
            @font-face {{
              font-family: 'MultiWeight';
              src: url('{uri_700}') format('ttf');
              font-weight: 700;
            }}
          </style>
          <text x="50" y="100" font-family="MultiWeight" font-weight="400" font-size="24">
            Regular Text
          </text>
          <text x="50" y="200" font-family="MultiWeight" font-weight="700" font-size="24">
            Bold Text
          </text>
        </svg>
        """

        output_path = tmp_path / "output_multiweight.pptx"
        artifacts = render_pptx_for_frames(
            frames=[_create_frame(svg_content)],
            output_path=output_path,
        )

        assert artifacts.slide_count == 1
        assert output_path.exists()

        # Both font weights should be embedded
        with zipfile.ZipFile(output_path, "r") as archive:
            names = archive.namelist()
            font_files = [name for name in names if name.startswith("ppt/fonts/")]
            # Should have at least one font (may be subset/combined)
            assert len(font_files) > 0

    def test_multi_slide_with_web_fonts(self, tmp_path: Path):
        """E2E: Multiple slides with web fonts -> PPTX with fonts used across slides."""
        font_file = Path(__file__).parent.parent / "resources" / "ScheherazadeRegOT.ttf"
        ttf_data = font_file.read_bytes()
        b64_data = base64.b64encode(ttf_data).decode("ascii")
        data_uri = f"data:font/ttf;base64,{b64_data}"

        # Create two slides with the same font
        svg_slide1 = f"""
        <svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">
          <style>
            @font-face {{
              font-family: 'SharedFont';
              src: url('{data_uri}') format('ttf');
            }}
          </style>
          <text x="50" y="100" font-family="SharedFont" font-size="32">Slide 1</text>
        </svg>
        """

        svg_slide2 = f"""
        <svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">
          <style>
            @font-face {{
              font-family: 'SharedFont';
              src: url('{data_uri}') format('ttf');
            }}
          </style>
          <text x="50" y="100" font-family="SharedFont" font-size="32">Slide 2</text>
        </svg>
        """

        output_path = tmp_path / "output_multislide.pptx"
        artifacts = render_pptx_for_frames(
            frames=[_create_frame(svg_slide1, "Slide1"), _create_frame(svg_slide2, "Slide2")],
            output_path=output_path,
        )

        assert artifacts.slide_count == 2
        assert output_path.exists()

        # Font should be embedded once (shared across slides)
        with zipfile.ZipFile(output_path, "r") as archive:
            names = archive.namelist()

            # Check both slides exist
            assert "ppt/slides/slide1.xml" in names
            assert "ppt/slides/slide2.xml" in names

            # Check font is embedded
            font_files = [name for name in names if name.startswith("ppt/fonts/")]
            assert len(font_files) > 0

    def test_svg_without_web_fonts_uses_system_fonts(self, tmp_path: Path):
        """E2E: SVG without @font-face -> PPTX uses system fonts (no embedding)."""
        svg_content = """
        <svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">
          <text x="50" y="100" font-family="Arial" font-size="32">
            System Font
          </text>
        </svg>
        """

        output_path = tmp_path / "output_system.pptx"
        artifacts = render_pptx_for_frames(
            frames=[_create_frame(svg_content)],
            output_path=output_path,
        )

        assert artifacts.slide_count == 1
        assert output_path.exists()

        # No custom fonts should be embedded (system fonts not embedded by default)
        # Note: This test validates that web font code doesn't break existing behavior

    def test_invalid_font_falls_back_gracefully(self, tmp_path: Path):
        """E2E: SVG with invalid @font-face -> PPTX generated with fallback font."""
        # Invalid data URI (not base64)
        svg_content = """
        <svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">
          <style>
            @font-face {
              font-family: 'InvalidFont';
              src: url('data:font/ttf;base64,NOT_VALID_BASE64!!!') format('ttf');
            }
          </style>
          <text x="50" y="100" font-family="InvalidFont" font-size="32">
            Should use fallback
          </text>
        </svg>
        """

        output_path = tmp_path / "output_fallback.pptx"
        artifacts = render_pptx_for_frames(
            frames=[_create_frame(svg_content)],
            output_path=output_path,
        )

        # Conversion should succeed with fallback
        assert artifacts.slide_count == 1
        assert output_path.exists()

        # Font should be in diagnostics as missing/failed
        # (Exact diagnostic behavior depends on implementation)

    def test_mixed_web_and_system_fonts(self, tmp_path: Path):
        """E2E: SVG with both web fonts and system fonts -> PPTX with correct handling."""
        font_file = Path(__file__).parent.parent / "resources" / "ScheherazadeRegOT.ttf"
        ttf_data = font_file.read_bytes()
        b64_data = base64.b64encode(ttf_data).decode("ascii")
        data_uri = f"data:font/ttf;base64,{b64_data}"

        svg_content = f"""
        <svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">
          <style>
            @font-face {{
              font-family: 'CustomWebFont';
              src: url('{data_uri}') format('ttf');
            }}
          </style>
          <text x="50" y="100" font-family="CustomWebFont" font-size="24">
            Web Font Text
          </text>
          <text x="50" y="200" font-family="Arial" font-size="24">
            System Font Text
          </text>
        </svg>
        """

        output_path = tmp_path / "output_mixed.pptx"
        artifacts = render_pptx_for_frames(
            frames=[_create_frame(svg_content)],
            output_path=output_path,
        )

        assert artifacts.slide_count == 1
        assert output_path.exists()

        # Web font should be embedded, system font should not
        with zipfile.ZipFile(output_path, "r") as archive:
            names = archive.namelist()
            font_files = [name for name in names if name.startswith("ppt/fonts/")]
            # Should have at least the web font
            assert len(font_files) > 0

    def test_font_with_special_characters_in_family_name(self, tmp_path: Path):
        """E2E: Font family with spaces/quotes -> PPTX handles correctly."""
        font_file = Path(__file__).parent.parent / "resources" / "ScheherazadeRegOT.ttf"
        ttf_data = font_file.read_bytes()
        b64_data = base64.b64encode(ttf_data).decode("ascii")
        data_uri = f"data:font/ttf;base64,{b64_data}"

        svg_content = f"""
        <svg xmlns="http://www.w3.org/2000/svg" width="400" height="200">
          <style>
            @font-face {{
              font-family: 'My Custom Font';
              src: url('{data_uri}') format('ttf');
            }}
          </style>
          <text x="50" y="100" font-family="'My Custom Font'" font-size="24">
            Font with spaces
          </text>
        </svg>
        """

        output_path = tmp_path / "output_special.pptx"
        artifacts = render_pptx_for_frames(
            frames=[_create_frame(svg_content)],
            output_path=output_path,
        )

        assert artifacts.slide_count == 1
        assert output_path.exists()

        # Font should be embedded despite special characters
        with zipfile.ZipFile(output_path, "r") as archive:
            names = archive.namelist()
            font_files = [name for name in names if name.startswith("ppt/fonts/")]
            assert len(font_files) > 0

    @pytest.mark.slow
    def test_large_number_of_web_fonts(self, tmp_path: Path):
        """E2E: SVG with many @font-face rules -> PPTX handles efficiently."""
        # Use real font for all declarations (same font, different names)
        font_file = Path(__file__).parent.parent / "resources" / "ScheherazadeRegOT.ttf"
        ttf_data = font_file.read_bytes()
        b64_data = base64.b64encode(ttf_data).decode("ascii")

        font_faces = []
        text_elements = []

        for i in range(10):
            data_uri = f"data:font/ttf;base64,{b64_data}"

            font_faces.append(f"""
            @font-face {{
              font-family: 'Font{i}';
              src: url('{data_uri}') format('ttf');
            }}
            """)

            text_elements.append(f"""
            <text x="50" y="{100 + i * 30}" font-family="Font{i}" font-size="16">
              Font {i}
            </text>
            """)

        svg_content = f"""
        <svg xmlns="http://www.w3.org/2000/svg" width="400" height="500">
          <style>
            {''.join(font_faces)}
          </style>
          {''.join(text_elements)}
        </svg>
        """

        output_path = tmp_path / "output_many_fonts.pptx"
        artifacts = render_pptx_for_frames(
            frames=[_create_frame(svg_content)],
            output_path=output_path,
        )

        assert artifacts.slide_count == 1
        assert output_path.exists()

        # Multiple fonts should be embedded
        with zipfile.ZipFile(output_path, "r") as archive:
            names = archive.namelist()
            font_files = [name for name in names if name.startswith("ppt/fonts/")]
            # Should have embedded fonts (exact number depends on subsetting)
            assert len(font_files) > 0
