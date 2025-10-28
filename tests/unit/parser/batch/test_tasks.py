"""Regression tests for batch tasks."""

from __future__ import annotations

from pathlib import Path

from svg2ooxml.core.parser.batch.tasks import convert_single_svg


def test_convert_single_svg_produces_pptx(tmp_path) -> None:
    svg = """
        <svg width="100" height="80" xmlns="http://www.w3.org/2000/svg">
            <rect x="10" y="10" width="40" height="20" fill="#FF0000"/>
        </svg>
    """
    conversion_options = {"output_dir": str(tmp_path)}

    result = convert_single_svg({"filename": "shape.svg", "content": svg}, conversion_options)

    assert result["success"] is True
    output_path = result["output_path"]
    assert output_path
    pptx_path = Path(output_path)
    assert pptx_path.exists()
    assert pptx_path.stat().st_size > 0
