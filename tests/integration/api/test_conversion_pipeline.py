from __future__ import annotations

from pathlib import Path

from svg2ooxml.api.models import RequestedFont, SVGFrame
from svg2ooxml.api.services.converter import render_pptx_for_frames


def _sample_frame() -> SVGFrame:
    return SVGFrame(
        name="Sample",
        svg_content=(
            "<svg xmlns='http://www.w3.org/2000/svg' width='10' height='10'>"
            "<rect width='10' height='10' fill='#336699'/>"
            "</svg>"
        ),
        width=10,
        height=10,
    )


def test_render_pptx_for_frames_produces_pptx(tmp_path: Path) -> None:
    output_path = tmp_path / "export.pptx"
    artifacts = render_pptx_for_frames([_sample_frame()], output_path)

    assert output_path.exists()
    assert artifacts.slide_count == 1
    assert artifacts.aggregated_trace.get("stage_totals", {}).get("parser:normalization") == 1


def test_render_pptx_reports_missing_fonts(tmp_path: Path) -> None:
    output_path = tmp_path / "missing-font.pptx"
    fonts = [RequestedFont.model_validate("DefinitelyMissingFont")]
    artifacts = render_pptx_for_frames([_sample_frame()], output_path, requested_fonts=fonts)

    assert "DefinitelyMissingFont" in artifacts.font_diagnostics.missing_fonts
