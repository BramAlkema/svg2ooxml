"""Visual regression tests for resvg integration features.

This test suite verifies that resvg-mode rendering produces visually correct
output for core features: blend modes, gradients, text, and composite filters.

Requirements:
- LibreOffice (soffice) must be available on PATH to render PPTX to PNG
- Baseline images must be generated first using tools/visual/update_baselines.py
- Install visual-testing dependencies: pip install svg2ooxml[visual-testing]

Usage:
    pytest tests/visual/test_resvg_visual.py -v

Baselines are stored in:
    tests/visual/baselines/resvg/

To regenerate baselines:
    python tools/visual/update_baselines.py --suite resvg
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.visual.differ import VisualDiffer
from tests.visual.helpers.diff import ImageDiffError
from tools.visual.renderer import LibreOfficeRenderer, VisualRendererError

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "resvg"
BASELINES_DIR = Path(__file__).parent / "baselines" / "resvg"


def _run_visual_test(
    fixture_name: str,
    tmp_path: Path,
    visual_tools,
    threshold: float = 0.95,
) -> None:
    """Helper to run a visual regression test for a given fixture.
    
    Args:
        fixture_name: Name of SVG fixture file (without .svg extension)
        tmp_path: pytest tmp_path fixture
        visual_tools: Visual test tools fixture
        threshold: SSIM threshold for pass/fail (default: 0.95)
    """
    renderer = visual_tools.renderer
    if isinstance(renderer, LibreOfficeRenderer) and not renderer.available:
        pytest.skip("LibreOffice (soffice) is not available on PATH.")
    
    # Build PPTX from SVG fixture
    svg_path = FIXTURES_DIR / f"{fixture_name}.svg"
    if not svg_path.exists():
        pytest.fail(f"Fixture not found: {svg_path}")
    
    svg_text = svg_path.read_text(encoding="utf-8")
    pptx_path = tmp_path / f"{fixture_name}.pptx"
    
    build_result = visual_tools.builder.build_from_svg(svg_text, pptx_path)
    assert build_result.slide_count == 1, f"Expected 1 slide, got {build_result.slide_count}"
    
    # Render PPTX to PNG
    render_dir = tmp_path / "render"
    try:
        slide_set = renderer.render(build_result.pptx_path, render_dir)
    except VisualRendererError as exc:
        pytest.skip(f"Rendering skipped: {exc}")
    
    assert slide_set.images, "Renderer did not produce any slide images."
    
    # Check baseline exists
    baseline_dir = BASELINES_DIR / fixture_name
    baseline_images = list(baseline_dir.glob("*.png")) if baseline_dir.exists() else []
    
    if not baseline_images:
        pytest.skip(
            f"Baseline images for {fixture_name} are missing. "
            f"Run tools/visual/update_baselines.py --suite resvg to generate them."
        )
    
    # Normalize filenames (renderer may produce slide_1.png, we want consistent names)
    generated_images = list(render_dir.glob("*.png"))
    if len(generated_images) == 1 and len(baseline_images) == 1:
        generated_image = generated_images[0]
        baseline_name = baseline_images[0].name
        target_path = render_dir / baseline_name
        if generated_image.name != baseline_name:
            target_path.write_bytes(generated_image.read_bytes())
            generated_image.unlink()
            generated_image = target_path
    
    # Compare using VisualDiffer (SSIM-based)
    from PIL import Image
    
    baseline_img = Image.open(baseline_images[0])
    actual_img = Image.open(generated_images[0] if len(generated_images) == 1 else target_path)
    
    differ = VisualDiffer(threshold=threshold)
    result = differ.compare(baseline_img, actual_img, generate_diff=True)
    
    if not result.passed:
        # Save diff for debugging
        diff_dir = tmp_path / "diff"
        diff_dir.mkdir(exist_ok=True)
        diff_path = diff_dir / f"{fixture_name}_diff.png"
        result.save_diff(diff_path)
        
        pytest.fail(
            f"Visual regression failed for {fixture_name}:\n"
            f"  SSIM: {result.ssim_score:.4f} (threshold: {threshold})\n"
            f"  Pixel diff: {result.pixel_diff_percentage:.2f}%\n"
            f"  Diff saved to: {diff_path}"
        )


@pytest.mark.visual
class TestBlendModes:
    """Test visual output of supported blend modes (normal, multiply, screen, darken, lighten)."""
    
    def test_blend_modes_rendering(self, tmp_path, visual_tools):
        """Test that all 5 supported blend modes render correctly."""
        _run_visual_test("blend_modes", tmp_path, visual_tools, threshold=0.95)


@pytest.mark.visual
class TestLinearGradients:
    """Test visual output of linear gradients with various configurations."""
    
    def test_linear_gradients_rendering(self, tmp_path, visual_tools):
        """Test horizontal, vertical, diagonal, and opacity gradients."""
        _run_visual_test("linear_gradients", tmp_path, visual_tools, threshold=0.95)


@pytest.mark.visual
class TestRadialGradients:
    """Test visual output of radial gradients with various configurations."""
    
    def test_radial_gradients_rendering(self, tmp_path, visual_tools):
        """Test simple, focal-offset, multi-stop, and userSpaceOnUse radial gradients.
        
        Note: Radial gradients may have slight variations due to DrawingML limitations
        (only supports circular gradients, not elliptical). Using threshold=0.92 for tolerance.
        """
        _run_visual_test("radial_gradients", tmp_path, visual_tools, threshold=0.92)


@pytest.mark.visual
class TestTextRendering:
    """Test visual output of text rendering with plain layouts."""
    
    def test_text_rendering(self, tmp_path, visual_tools):
        """Test simple, bold, italic, gradient fill, and translated text.
        
        Note: Font rendering may vary slightly across systems. Using threshold=0.93.
        """
        _run_visual_test("text_rendering", tmp_path, visual_tools, threshold=0.93)


@pytest.mark.visual
class TestCompositeFilters:
    """Test visual output of feComposite filters (simple masking operations)."""
    
    def test_composite_filters_rendering(self, tmp_path, visual_tools):
        """Test in, out, atop, and over composite operators."""
        _run_visual_test("composite_filters", tmp_path, visual_tools, threshold=0.95)


@pytest.mark.visual
class TestIntegration:
    """Integration tests combining multiple resvg features."""
    
    @pytest.mark.parametrize("fixture", [
        "blend_modes",
        "linear_gradients",
        "radial_gradients",
        "text_rendering",
        "composite_filters",
    ])
    def test_all_resvg_features(self, fixture, tmp_path, visual_tools):
        """Parametrized test running all fixtures."""
        # Use feature-specific thresholds
        thresholds = {
            "blend_modes": 0.95,
            "linear_gradients": 0.95,
            "radial_gradients": 0.92,  # Tolerance for DrawingML limitations
            "text_rendering": 0.93,    # Tolerance for font rendering
            "composite_filters": 0.95,
        }
        threshold = thresholds.get(fixture, 0.95)
        _run_visual_test(fixture, tmp_path, visual_tools, threshold=threshold)
