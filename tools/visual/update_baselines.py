#!/usr/bin/env python3
"""Generate or refresh visual regression baselines using LibreOffice."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
for entry in (REPO_ROOT, SRC_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from tools.visual.builder import PptxBuilder
from tools.visual.golden import GoldenRepository
from tools.visual.renderer import LibreOfficeRenderer, VisualRendererError, default_renderer

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("update_baselines")

SCENARIOS = {
    "rect_scene": {
        "source": Path("tests/visual/fixtures/simple_rect.svg"),
        "golden": Path("rect_scene"),
    },
    "simple-rect": {
        "source": Path("tests/visual/fixtures/simple_rect.svg"),
        "golden": Path("w3c/simple-rect"),
    },
    "struct-use-10-f": {
        "source": Path("tests/svg/struct-use-10-f.svg"),
        "golden": Path("w3c/struct-use-10-f"),
    },
    "svg2pptx_demo": {
        "source": Path("../svg2pptx/pipeline/validation_results/basic_rectangle_balanced.pptx"),
        "golden": Path("svg2pptx_demo"),
    },
}

RESVG_FIXTURES = {
    "blend_modes": Path("tests/visual/fixtures/resvg/blend_modes.svg"),
    "composite_filters": Path("tests/visual/fixtures/resvg/composite_filters.svg"),
    "linear_gradients": Path("tests/visual/fixtures/resvg/linear_gradients.svg"),
    "radial_gradients": Path("tests/visual/fixtures/resvg/radial_gradients.svg"),
    "text_rendering": Path("tests/visual/fixtures/resvg/text_rendering.svg"),
}
RESVG_BASELINES_DIR = Path("tests/visual/baselines/resvg")


def generate_baseline(name: str, renderer: LibreOfficeRenderer, builder: PptxBuilder, golden: GoldenRepository) -> None:
    scenario = SCENARIOS.get(name)
    if scenario is None:
        raise SystemExit(f"Unknown scenario {name!r}. Available: {', '.join(SCENARIOS)}")

    if isinstance(scenario, dict):
        fixture_path = Path(scenario.get("source"))
        golden_subdir = scenario.get("golden")
    else:
        fixture_path = Path(scenario)
        golden_subdir = None

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

    golden_subdir = scenario.get("golden") if isinstance(scenario, dict) else None
    target_dir = golden.ensure(golden_subdir or name)
    for image in slide_set.images:
        target_path = target_dir / image.name
        logger.info("Writing %s", target_path)
        target_path.write_bytes(Path(image).read_bytes())


def generate_resvg_baseline(
    name: str,
    renderer: LibreOfficeRenderer,
    builder: PptxBuilder,
    baseline_root: Path,
) -> None:
    fixture_path = RESVG_FIXTURES.get(name)
    if fixture_path is None:
        raise SystemExit(
            f"Unknown resvg fixture {name!r}. Available: {', '.join(sorted(RESVG_FIXTURES))}"
        )

    work_dir = Path(".visual_tmp") / f"resvg_{name}"
    work_dir.mkdir(parents=True, exist_ok=True)
    render_dir = work_dir / "render"
    render_dir.mkdir(exist_ok=True)

    svg_text = fixture_path.read_text(encoding="utf-8")
    pptx_path = work_dir / f"{name}.pptx"
    builder.build_from_svg(svg_text, pptx_path)

    try:
        slide_set = renderer.render(pptx_path, render_dir)
    except VisualRendererError as exc:
        raise SystemExit(f"Rendering failed: {exc}") from exc

    if not slide_set.images:
        raise SystemExit("Renderer produced no slides.")

    target_dir = baseline_root / name
    target_dir.mkdir(parents=True, exist_ok=True)
    for image in slide_set.images:
        target_path = target_dir / image.name
        logger.info("Writing %s", target_path)
        target_path.write_bytes(Path(image).read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scenarios",
        nargs="*",
        help="Scenario or fixture names to refresh (default: all in selected mode).",
    )
    parser.add_argument(
        "--suite",
        choices=["resvg"],
        help="Generate baselines for a named suite (e.g. resvg).",
    )
    parser.add_argument(
        "--soffice",
        help="Explicit path to the soffice binary (defaults to PATH lookup).",
    )
    parser.add_argument(
        "--soffice-profile",
        help="LibreOffice user profile directory passed via -env:UserInstallation.",
    )
    args = parser.parse_args()

    user_installation = args.soffice_profile or os.getenv("SVG2OOXML_SOFFICE_USER_INSTALL")
    if args.soffice:
        renderer = LibreOfficeRenderer(
            soffice_path=args.soffice,
            user_installation=user_installation,
        )
    else:
        soffice_override = os.getenv("SVG2OOXML_SOFFICE_PATH")
        if soffice_override:
            renderer = LibreOfficeRenderer(
                soffice_path=soffice_override,
                user_installation=user_installation,
            )
        else:
            renderer = default_renderer(user_installation=user_installation)
    if not renderer.available:
        raise SystemExit("LibreOffice (soffice) is not available. Please install it first.")

    filter_strategy = os.getenv("SVG2OOXML_VISUAL_FILTER_STRATEGY", "resvg")
    slide_size_mode = os.getenv("SVG2OOXML_SLIDE_SIZE_MODE", "same")
    builder = PptxBuilder(filter_strategy=filter_strategy, slide_size_mode=slide_size_mode)
    golden = GoldenRepository()

    if args.suite == "resvg":
        baseline_root = RESVG_BASELINES_DIR
        baseline_root.mkdir(parents=True, exist_ok=True)
        fixture_names = args.scenarios or sorted(RESVG_FIXTURES)
        for fixture in fixture_names:
            logger.info("Generating resvg baseline for %s", fixture)
            generate_resvg_baseline(fixture, renderer, builder, baseline_root)
    else:
        scenario_names = args.scenarios or sorted(SCENARIOS)
        for scenario in scenario_names:
            logger.info("Generating baseline for %s", scenario)
            generate_baseline(scenario, renderer, builder, golden)

    logger.info("Baseline update complete.")


if __name__ == "__main__":
    main()
