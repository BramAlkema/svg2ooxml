"""Tests for slide bundle serialization boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from svg2ooxml.core.parser.batch.bundles import (
    job_dir,
    new_job_id,
    read_slide_bundle,
    write_slide_bundle,
)
from svg2ooxml.drawingml.assets import (
    AssetRegistrySnapshot,
    FontAsset,
    MediaAsset,
)
from svg2ooxml.drawingml.result import DrawingMLRenderResult
from svg2ooxml.ir.text import EmbeddedFontPlan


def test_job_dir_rejects_path_like_job_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsafe batch job id"):
        job_dir("../escape", tmp_path)

    assert not (tmp_path.parent / "escape").exists()


def test_new_job_id_sanitizes_prefix() -> None:
    job_id = new_job_id("../bad prefix")

    assert job_id.startswith("bad-prefix-")


def test_read_slide_bundle_rejects_media_path_escape(tmp_path: Path) -> None:
    bundle_dir = _write_minimal_bundle(tmp_path)
    metadata = json.loads((bundle_dir / "metadata.json").read_text(encoding="utf-8"))
    metadata["media"] = [
        {
            "relationship_id": "rIdMedia1",
            "filename": "image.png",
            "content_type": "image/png",
            "data_path": "../secret.bin",
        }
    ]
    (bundle_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="escapes bundle directory"):
        read_slide_bundle(bundle_dir)


def test_read_slide_bundle_rejects_font_byte_path_escape(tmp_path: Path) -> None:
    bundle_dir = _write_minimal_bundle(tmp_path)
    metadata = json.loads((bundle_dir / "metadata.json").read_text(encoding="utf-8"))
    metadata["fonts"] = [
        {
            "shape_id": 1,
            "plan": {
                "font_family": "Test",
                "requires_embedding": True,
                "subset_strategy": "full",
                "glyph_count": 1,
                "metadata": {"font_data": {"__bytes__": "../secret.bin"}},
            },
        }
    ]
    (bundle_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="escapes bundle directory"):
        read_slide_bundle(bundle_dir)


def test_write_and_read_slide_bundle_round_trips_assets(tmp_path: Path) -> None:
    font_plan = EmbeddedFontPlan(
        font_family="Test",
        requires_embedding=True,
        subset_strategy="full",
        glyph_count=1,
        relationship_hint="rIdFont1",
        metadata={"font_data": b"font-bytes"},
    )
    result = DrawingMLRenderResult(
        slide_xml="<p:sld/>",
        slide_size=(100, 80),
        shape_xml=("<p:sp/>",),
        assets=AssetRegistrySnapshot(
            media=(
                MediaAsset(
                    relationship_id="rIdMedia1",
                    filename="../unsafe.txt",
                    content_type="image/png",
                    data=b"png",
                ),
            ),
            fonts=(FontAsset(shape_id=7, plan=font_plan),),
            masks=(
                {
                    "relationship_id": "rIdMask1",
                    "part_name": "/ppt/masks/mask1.png",
                    "content_type": "image/png",
                    "data": b"mask",
                },
            ),
        ),
    )

    bundle_dir = write_slide_bundle(result, "job-1", 1, base_dir=tmp_path)
    restored = read_slide_bundle(bundle_dir)

    assert restored.slide_xml == "<p:sld/>"
    assert restored.slide_size == (100, 80)
    assert restored.shape_xml == ("<p:sp/>",)
    assert restored.assets.media[0].data == b"png"
    assert restored.assets.fonts[0].shape_id == 7
    assert restored.assets.fonts[0].plan.metadata["font_data"] == b"font-bytes"
    assert restored.assets.masks[0]["data"] == b"mask"


def _write_minimal_bundle(tmp_path: Path) -> Path:
    bundle_dir = tmp_path / "job" / "slide_0001"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "slide.xml").write_text("<p:sld/>", encoding="utf-8")
    (bundle_dir / "metadata.json").write_text(
        json.dumps({"slide_size": [100, 80], "shape_xml": []}),
        encoding="utf-8",
    )
    return bundle_dir
