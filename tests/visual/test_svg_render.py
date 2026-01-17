"""Visual regression test that renders an SVG through the full pptx pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.visual.renderer import LibreOfficeRenderer, VisualRendererError

FIXTURE_SVG = Path(__file__).parent / "fixtures" / "simple_rect.svg"
GOLDEN_DIR = "rect_scene"


@pytest.mark.visual
def test_simple_rect_scene(tmp_path, visual_tools) -> None:
    renderer = visual_tools.renderer
    if isinstance(renderer, LibreOfficeRenderer) and not renderer.available:
        pytest.skip("LibreOffice (soffice) is not available on PATH.")

    svg_text = FIXTURE_SVG.read_text(encoding="utf-8")
    pptx_path = tmp_path / "scene.pptx"
    build_result = visual_tools.builder.build_from_svg(svg_text, pptx_path)
    assert build_result.slide_count == 1

    render_dir = tmp_path / "render"
    try:
        slide_set = renderer.render(build_result.pptx_path, render_dir)
    except VisualRendererError as exc:
        pytest.skip(f"Rendering skipped: {exc}")
    assert slide_set.images, "Renderer did not produce any slide images."

    baseline_dir = visual_tools.golden.path_for(GOLDEN_DIR)
    if not any(baseline_dir.glob("*.png")):
        pytest.skip(
            "Baseline images for rect_scene are missing. "
            "Run tools/visual/update_baselines.py to generate them."
        )
    generated_images = list(render_dir.glob("*.png"))
    baseline_images = sorted(baseline_dir.glob("*.png"))
    if len(generated_images) == 1 and len(baseline_images) == 1:
        generated_image = generated_images[0]
        baseline_name = baseline_images[0].name
        target_path = render_dir / baseline_name
        if generated_image.name != baseline_name:
            target_path.write_bytes(generated_image.read_bytes())
            generated_image.unlink()

    diff_dir = tmp_path / "diff"
    visual_tools.diff.compare_directories(render_dir, baseline_dir, diff_dir=diff_dir)
