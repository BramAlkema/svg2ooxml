"""Tests for the font embedding engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from svg2ooxml.services.fonts.embedding import FontEmbeddingEngine, FontEmbeddingRequest
from svg2ooxml.services.fonts.fontforge_utils import FONTFORGE_AVAILABLE, open_font


def _resource_font_path() -> Path:
    return Path(__file__).resolve().parents[2] / "resources" / "ScheherazadeRegOT.ttf"


def _make_request(tmp_path: Path) -> FontEmbeddingRequest:
    font_path = tmp_path / "ScheherazadeRegOT.ttf"
    font_path.write_bytes(_resource_font_path().read_bytes())
    return FontEmbeddingRequest(
        font_path=str(font_path),
        glyph_ids=(65, 66, 67),
        preserve_hinting=True,
        subset_strategy="glyph",
        metadata={"font_family": "Stub"},
    )


@pytest.mark.skipif(not FONTFORGE_AVAILABLE, reason="FontForge required for glyph subsetting")
def test_subset_font_uses_cache(monkeypatch, tmp_path) -> None:
    engine = FontEmbeddingEngine()
    request = _make_request(tmp_path)

    monkeypatch.setattr(engine, "_read_embedding_permission", lambda _path, _data=None: "installable")

    result_a = engine.subset_font(request)
    result_b = engine.subset_font(request)

    assert result_a is not None
    assert result_b is result_a
    assert result_a.bytes_written > 0
    assert engine.stats()["subset_success"] == 1
    assert engine.stats()["subset_cache_hits"] == 1


def test_subset_font_respects_permissions(monkeypatch, tmp_path) -> None:
    engine = FontEmbeddingEngine()
    request = _make_request(tmp_path)

    monkeypatch.setattr(engine, "_read_embedding_permission", lambda _path, _data=None: "restricted")

    result = engine.subset_font(request)

    assert result is None
    assert engine.stats()["subset_failures"] == 1


def test_subset_font_strategy_none_reads_bytes(monkeypatch, tmp_path) -> None:
    engine = FontEmbeddingEngine()
    request = _make_request(tmp_path)
    request = FontEmbeddingRequest(
        font_path=request.font_path,
        glyph_ids=request.glyph_ids,
        preserve_hinting=False,
        subset_strategy="none",
        metadata={},
    )

    monkeypatch.setattr(engine, "_read_embedding_permission", lambda _path, _data=None: "installable")

    result = engine.subset_font(request)

    assert result is not None
    assert result.bytes_written == len(Path(request.font_path).read_bytes())
    assert result.packaging_metadata["font_data"] == Path(request.font_path).read_bytes()


def test_can_embed_handles_missing_font(tmp_path) -> None:
    engine = FontEmbeddingEngine()

    assert engine.can_embed(str(tmp_path / "missing.ttf")) is False


@pytest.mark.skipif(not FONTFORGE_AVAILABLE, reason="FontForge required for ligature subsetting")
def test_subset_includes_ligature_glyph(tmp_path) -> None:
    pytest.importorskip("fontforge")
    import fontforge  # type: ignore[import-not-found]

    font = fontforge.font()
    font.encoding = "UnicodeFull"
    font.familyname = "LigatureTest"
    font.fullname = "LigatureTest Regular"
    font.fontname = "LigatureTest-Regular"

    font.createChar(ord("f"), "f").width = 500
    font.createChar(ord("i"), "i").width = 500
    lig = font.createChar(-1, "fi")
    lig.width = 500

    font.addLookup(
        "liga",
        "gsub_ligature",
        (),
        (("liga", (("latn", ("dflt",)),)),),
    )
    font.addLookupSubtable("liga", "liga_sub")
    lig.addPosSub("liga_sub", ("f", "i"))

    font_path = tmp_path / "ligature.ttf"
    font.generate(str(font_path))
    font.close()

    engine = FontEmbeddingEngine()
    request = FontEmbeddingRequest(
        font_path=str(font_path),
        characters=tuple("fi"),
        metadata={"font_family": "LigatureTest"},
    )
    result = engine.subset_font(request)
    assert result is not None

    subset_bytes = result.packaging_metadata.get("subset_bytes")
    assert isinstance(subset_bytes, (bytes, bytearray))

    with open_font(bytes(subset_bytes), suffix=".ttf") as subset_font:
        glyph_names = {glyph.glyphname for glyph in subset_font.glyphs()}
    assert "fi" in glyph_names
