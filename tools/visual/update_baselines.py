#!/usr/bin/env python3
"""Generate or refresh visual regression baselines using LibreOffice."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
for entry in (REPO_ROOT, SRC_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from tests.visual.helpers.builder import PptxBuilder
from tests.visual.helpers.golden import GoldenRepository
from tools.visual.renderer import LibreOfficeRenderer, VisualRendererError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("update_baselines")

SCENARIOS = {
    "rect_scene": Path("tests/visual/fixtures/simple_rect.svg"),
    "svg2pptx_demo": Path("../svg2pptx/pipeline/validation_results/basic_rectangle_balanced.pptx"),
}


def generate_baseline(name: str, renderer: LibreOfficeRenderer, builder: PptxBuilder, golden: GoldenRepository) -> None:
    fixture = SCENARIOS.get(name)
    if fixture is None:
        raise SystemExit(f"Unknown scenario {name!r}. Available: {', '.join(SCENARIOS)}")
    fixture_path = Path(fixture)

    work_dir = Path(".visual_tmp") / name
    work_dir.mkdir(parents=True, exist_ok=True)
    render_dir = work_dir / "render"
    render_dir.mkdir(exist_ok=True)

    if fixture_path.suffix.lower() == ".pptx":
        pptx_path = fixture_path
    else:
        svg_text = fixture_path.read_text(encoding="utf-8")
        pptx_path = work_dir / f"{name}.pptx"
        builder.build_from_svg(svg_text, pptx_path)

    try:
        slide_set = renderer.render(pptx_path, render_dir)
    except VisualRendererError as exc:
        raise SystemExit(f"Rendering failed: {exc}") from exc

    if not slide_set.images:
        raise SystemExit("Renderer produced no slides.")

    target_dir = golden.ensure(name)
    for image in slide_set.images:
        target_path = target_dir / image.name
        logger.info("Writing %s", target_path)
        target_path.write_bytes(Path(image).read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scenarios",
        nargs="*",
        default=sorted(SCENARIOS),
        help="Scenario names to refresh (default: all).",
    )
    parser.add_argument(
        "--soffice",
        help="Explicit path to the soffice binary (defaults to PATH lookup).",
    )
    args = parser.parse_args()

    renderer = LibreOfficeRenderer(soffice_path=args.soffice)
    if not renderer.available:
        raise SystemExit("LibreOffice (soffice) is not available. Please install it first.")

    builder = PptxBuilder()
    golden = GoldenRepository()

    for scenario in args.scenarios:
        logger.info("Generating baseline for %s", scenario)
        generate_baseline(scenario, renderer, builder, golden)

    logger.info("Baseline update complete.")


if __name__ == "__main__":
    main()
