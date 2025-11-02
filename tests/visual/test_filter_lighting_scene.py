"""Visual comparison between resvg and legacy lighting fallback outputs."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat  # type: ignore[import]

from tests.visual.helpers.builder import PptxBuilder
from tools.visual.renderer import LibreOfficeRenderer, VisualRendererError

FIXTURE_SVG = Path(__file__).parent / "fixtures" / "lighting_scene.svg"


def _render_slide(builder: PptxBuilder, svg_text: str, pptx_path: Path, render_dir: Path, renderer) -> Path:
    build_result = builder.build_from_svg(svg_text, pptx_path)
    assert build_result.slide_count == 1
    try:
        slide_set = renderer.render(build_result.pptx_path, render_dir)
    except VisualRendererError as exc:  # pragma: no cover - renderer optional
        pytest.skip(f"Rendering skipped: {exc}")
    assert slide_set.images, "Renderer did not produce any slide images."
    return slide_set.images[0]


def _diff_metrics(candidate: Path, baseline: Path) -> tuple[float, float]:
    generated = Image.open(candidate).convert("RGBA")
    reference = Image.open(baseline).convert("RGBA")
    diff = ImageChops.difference(generated, reference)
    stats = ImageStat.Stat(diff)
    max_delta = max(extreme[1] for extreme in stats.extrema)
    mean_delta = max(stats.mean)
    return float(max_delta), float(mean_delta)


@pytest.mark.visual
def test_lighting_scene_resvg_vs_legacy(tmp_path, visual_tools) -> None:
    renderer = visual_tools.renderer
    if isinstance(renderer, LibreOfficeRenderer) and not renderer.available:
        pytest.skip("LibreOffice (soffice) is not available on PATH.")

    svg_text = FIXTURE_SVG.read_text(encoding="utf-8")

    resvg_builder = PptxBuilder(filter_strategy="resvg")
    legacy_builder = PptxBuilder(filter_strategy="legacy")

    resvg_image = _render_slide(
        resvg_builder,
        svg_text,
        tmp_path / "lighting_resvg.pptx",
        tmp_path / "resvg_render",
        renderer,
    )
    legacy_image = _render_slide(
        legacy_builder,
        svg_text,
        tmp_path / "lighting_legacy.pptx",
        tmp_path / "legacy_render",
        renderer,
    )

    max_delta, mean_delta = _diff_metrics(resvg_image, legacy_image)

    # Quantify the delta between strategies; enforce that any divergence stays modest.
    assert max_delta <= 32.0
    assert mean_delta <= 8.0
