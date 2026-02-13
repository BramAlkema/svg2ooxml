"""Tests for slide bundle stitching."""

from __future__ import annotations

from pathlib import Path

from svg2ooxml.core.parser.batch.tasks import (
    process_svg_batch_to_bundles,
    stitch_svg_job,
)


def test_bundle_and_stitch_pptx(tmp_path: Path) -> None:
    svg1 = """
        <svg width="120" height="80" xmlns="http://www.w3.org/2000/svg">
            <rect x="10" y="10" width="40" height="20" fill="#FF0000"/>
        </svg>
    """
    svg2 = """
        <svg width="120" height="80" xmlns="http://www.w3.org/2000/svg">
            <circle cx="40" cy="40" r="20" fill="#00AAFF"/>
        </svg>
    """
    bundle_root = tmp_path / "bundles"
    job_id = "test-bundle-job"

    result = process_svg_batch_to_bundles(
        [
            {"filename": "slide1.svg", "content": svg1},
            {"filename": "slide2.svg", "content": svg2},
        ],
        conversion_options={"bundle_dir": str(bundle_root)},
        job_id=job_id,
    )

    assert result["success"] is True
    assert result["job_id"] == job_id

    output_path = tmp_path / "stitched.pptx"
    stitch_result = stitch_svg_job(
        job_id,
        output_path,
        bundle_dir=bundle_root,
    )

    assert stitch_result["success"] is True
    assert output_path.exists()
    assert output_path.stat().st_size > 0
