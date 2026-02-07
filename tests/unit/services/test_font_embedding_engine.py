"""Tests for the font embedding engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from svg2ooxml.services.fonts.embedding import FontEmbeddingEngine, FontEmbeddingRequest
from svg2ooxml.services.fonts.fontforge_utils import FONTFORGE_AVAILABLE


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
