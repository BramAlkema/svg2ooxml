"""Tests for OTF to TTF conversion (ported from tokenmoulds)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

pytest.importorskip("fontTools")

from fontTools.fontBuilder import FontBuilder  # noqa: E402
from fontTools.pens.t2CharStringPen import T2CharStringPen  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

from svg2ooxml.services.fonts.otf2ttf import (  # noqa: E402
    convert_font_bytes_for_embedding,
    convert_font_for_embedding,
    is_otf,
    is_ttf,
    otf_to_ttf,
)

RESOURCES = Path(__file__).resolve().parents[3] / "resources"
SCHEHERAZADE_TTF = RESOURCES / "ScheherazadeRegOT.ttf"


def _build_synthetic_otf() -> bytes:
    """Build a minimal CFF-flavoured OpenType font in-memory.

    Two glyphs (.notdef and 'A'), just enough structure for fontTools to
    serialise a valid ``OTTO``-flagged sfnt container. Used as a throwaway
    fixture for CFF→glyf conversion tests — avoids vendoring a binary font.
    """
    fb = FontBuilder(1024, isTTF=False)
    fb.setupGlyphOrder([".notdef", "A"])
    fb.setupCharacterMap({65: "A"})

    a_pen = T2CharStringPen(600, None)
    a_pen.moveTo((50, 0))
    a_pen.lineTo((550, 0))
    a_pen.lineTo((550, 700))
    a_pen.lineTo((50, 700))
    a_pen.closePath()

    char_strings = {
        ".notdef": T2CharStringPen(600, None).getCharString(),
        "A": a_pen.getCharString(),
    }
    fb.setupCFF("SvgToOoxmlTest", {"FullName": "SvgToOoxml Test"}, char_strings, {})
    fb.setupHorizontalMetrics({".notdef": (600, 0), "A": (600, 50)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "SvgToOoxmlTest", "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=800, usWinAscent=800, usWinDescent=200)
    fb.setupPost()

    buf = io.BytesIO()
    fb.save(buf)
    return buf.getvalue()


@pytest.fixture(scope="module")
def synthetic_otf_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    otf_dir = tmp_path_factory.mktemp("otf_fixture")
    otf_path = otf_dir / "synthetic.otf"
    otf_path.write_bytes(_build_synthetic_otf())
    return otf_path


class TestFontTypeDetection:
    @pytest.mark.skipif(not SCHEHERAZADE_TTF.exists(), reason="TTF fixture missing")
    def test_is_ttf_with_ttf_file(self) -> None:
        assert is_ttf(SCHEHERAZADE_TTF) is True

    @pytest.mark.skipif(not SCHEHERAZADE_TTF.exists(), reason="TTF fixture missing")
    def test_is_otf_with_ttf_file(self) -> None:
        assert is_otf(SCHEHERAZADE_TTF) is False

    def test_is_otf_with_otf_file(self, synthetic_otf_path: Path) -> None:
        assert is_otf(synthetic_otf_path) is True

    def test_is_ttf_with_otf_file(self, synthetic_otf_path: Path) -> None:
        assert is_ttf(synthetic_otf_path) is False


class TestOtfToTtfConversion:
    def test_otf_to_ttf_produces_valid_ttf(self, synthetic_otf_path: Path) -> None:
        ttf_data = otf_to_ttf(synthetic_otf_path)
        assert len(ttf_data) > 0

        font = TTFont(io.BytesIO(ttf_data))
        assert "glyf" in font
        assert "CFF " not in font
        assert "CFF2" not in font

    def test_otf_to_ttf_preserves_glyph_count(
        self, synthetic_otf_path: Path
    ) -> None:
        original = TTFont(synthetic_otf_path)
        original_count = len(original.getGlyphOrder())

        converted = TTFont(io.BytesIO(otf_to_ttf(synthetic_otf_path)))
        assert len(converted.getGlyphOrder()) == original_count

    @pytest.mark.skipif(not SCHEHERAZADE_TTF.exists(), reason="TTF fixture missing")
    def test_otf_to_ttf_with_ttf_returns_glyf_font(self) -> None:
        ttf_data = otf_to_ttf(SCHEHERAZADE_TTF)
        font = TTFont(io.BytesIO(ttf_data))
        assert "glyf" in font


class TestConvertFontForEmbedding:
    def test_convert_otf_returns_ttf(self, synthetic_otf_path: Path) -> None:
        ttf_data = convert_font_for_embedding(synthetic_otf_path)
        font = TTFont(io.BytesIO(ttf_data))
        assert "glyf" in font
        assert "CFF " not in font

    @pytest.mark.skipif(not SCHEHERAZADE_TTF.exists(), reason="TTF fixture missing")
    def test_convert_ttf_returns_ttf(self) -> None:
        ttf_data = convert_font_for_embedding(SCHEHERAZADE_TTF)
        font = TTFont(io.BytesIO(ttf_data))
        assert "glyf" in font

    def test_convert_missing_font_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            convert_font_for_embedding(Path("/nonexistent/font.otf"))

    @pytest.mark.skipif(not SCHEHERAZADE_TTF.exists(), reason="TTF fixture missing")
    def test_convert_font_bytes_strips_gsub_preserves_gpos(self) -> None:
        original = TTFont(SCHEHERAZADE_TTF)
        try:
            if "GSUB" not in original:
                pytest.skip("Test font lacks GSUB table")
            if "GPOS" not in original:
                pytest.skip("Test font lacks GPOS table")
        finally:
            original.close()

        raw_bytes = SCHEHERAZADE_TTF.read_bytes()
        sanitized = convert_font_bytes_for_embedding(
            raw_bytes,
            strip_opentype_features=True,
        )
        stripped = TTFont(io.BytesIO(sanitized))
        try:
            assert "GSUB" not in stripped
            assert "GPOS" in stripped
        finally:
            stripped.close()
