"""Visual regression test that renders an SVG through the full pptx pipeline."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools.visual.browser_renderer import BrowserRenderError
from tools.visual.diff import VisualDiffer
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
        if os.getenv("SVG2OOXML_VISUAL_BROWSER_COMPARE") != "1":
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

    if not generated_images:
        pytest.fail("Renderer did not generate any PNG images.")

    actual_path = generated_images[0]
    if len(generated_images) == 1 and len(baseline_images) == 1:
        actual_path = render_dir / baseline_images[0].name

    diff_dir = tmp_path / "diff"
    if baseline_images:
        visual_tools.diff.compare_directories(render_dir, baseline_dir, diff_dir=diff_dir)

    if os.getenv("SVG2OOXML_VISUAL_BROWSER_COMPARE") == "1":
        browser_renderer = getattr(visual_tools, "browser_renderer", None)
        if not browser_renderer or not browser_renderer.available:
            pytest.skip("Playwright browser renderer is not available.")

        browser_threshold = float(os.getenv("SVG2OOXML_VISUAL_BROWSER_THRESHOLD", "0.90"))
        browser_path = tmp_path / "simple_rect_browser.png"
        try:
            browser_renderer.render_svg(svg_text, browser_path)
        except BrowserRenderError as exc:
            pytest.fail(f"Browser render failed: {exc}")

        from PIL import Image

        browser_img = Image.open(browser_path)
        actual_img = Image.open(actual_path)
        differ = VisualDiffer(threshold=browser_threshold)
        result = differ.compare(browser_img, actual_img, generate_diff=True)

        if not result.passed:
            diff_dir.mkdir(exist_ok=True)
            diff_path = diff_dir / "simple_rect_browser_diff.png"
            result.save_diff(diff_path)
            pytest.fail(
                "Browser parity failed for simple_rect:\n"
                f"  SSIM: {result.ssim_score:.4f} (threshold: {browser_threshold})\n"
                f"  Pixel diff: {result.pixel_diff_percentage:.2f}%\n"
                f"  Diff saved to: {diff_path}"
            )
