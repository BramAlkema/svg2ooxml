"""Coordinator helper tests."""

from __future__ import annotations

from pathlib import Path

from svg2ooxml.core.parser.batch.coordinator import convert_svg_batch_parallel


def test_convert_svg_batch_parallel_inline(tmp_path: Path) -> None:
    svg = """
        <svg width="120" height="80" xmlns="http://www.w3.org/2000/svg">
            <rect x="10" y="10" width="40" height="20" fill="#FF0000"/>
        </svg>
    """
    output_path = tmp_path / "out.pptx"
    bundle_dir = tmp_path / "bundles"

    result = convert_svg_batch_parallel(
        [{"filename": "slide1.svg", "content": svg}],
        output_path,
        conversion_options={"bundle_dir": str(bundle_dir)},
        force_inline=True,
        openxml_required=False,
    )

    assert result["success"] is True
    assert output_path.exists()
    assert output_path.stat().st_size > 0
