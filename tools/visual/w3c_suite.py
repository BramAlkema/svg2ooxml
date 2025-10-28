#!/usr/bin/env python3
"""Run a curated set of SVG → PPTX comparisons for W3C fixtures."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable

from tests.visual.helpers.builder import PptxBuilder
from tests.visual.helpers.diff import ImageDiff, ImageDiffError
from tests.visual.helpers.golden import GoldenRepository
from tools.visual.renderer import VisualRendererError, default_renderer

logger = logging.getLogger("w3c_suite")


SCENARIOS = {
    "struct-use-10-f": Path("tests/svg/struct-use-10-f.svg"),
    "simple-rect": Path("tests/visual/fixtures/simple_rect.svg"),
}


def _resolve_scenarios(names: Iterable[str] | None) -> list[tuple[str, Path]]:
    if not names:
        return [(name, path) for name, path in SCENARIOS.items()]
    resolved: list[tuple[str, Path]] = []
    for name in names:
        svg = SCENARIOS.get(name)
        if svg is None:
            raise SystemExit(f"Unknown scenario '{name}'. Available: {', '.join(SCENARIOS)}")
        resolved.append((name, svg))
    return resolved


def run_suite(names: Iterable[str] | None, output_dir: Path) -> None:
    renderer = default_renderer()
    if not renderer.available:
        raise SystemExit(
            "LibreOffice (soffice) is not available. Install it or set "
            "SVG2OOXML_SOFFICE_PATH before running the suite."
        )

    builder = PptxBuilder()
    golden = GoldenRepository(Path("tests/visual/golden"))
    diff = ImageDiff()

    for name, svg_path in _resolve_scenarios(names):
        logger.info("Running scenario %s", name)
        if not svg_path.exists():
            logger.warning("Skipping %s – SVG missing: %s", name, svg_path)
            continue

        scenario_dir = output_dir / name
        render_dir = scenario_dir / "render"
        diff_dir = scenario_dir / "diff"
        render_dir.mkdir(parents=True, exist_ok=True)
        diff_dir.mkdir(parents=True, exist_ok=True)

        pptx_path = scenario_dir / "presentation.pptx"
        svg_text = svg_path.read_text(encoding="utf-8")
        build_result = builder.build_from_svg(svg_text, pptx_path)
        logger.info("%s: generated PPTX (%d slide(s))", name, build_result.slide_count)

        try:
            rendered = renderer.render(build_result.pptx_path, render_dir)
        except VisualRendererError as exc:
            logger.warning("%s: rendering failed – %s", name, exc)
            continue
        logger.info("%s: rendered %d slide image(s)", name, len(rendered.images))

        baseline_dir = golden.path_for(Path("w3c") / name)
        if not baseline_dir.exists() or not any(baseline_dir.glob("*.png")):
            logger.warning(
                "%s: baseline images not found at %s. "
                "Run `python -m tools.visual.update_baselines %s` once baselines are prepared.",
                name,
                baseline_dir,
                name,
            )
            continue

        generated_images = list(render_dir.glob("*.png"))
        baseline_images = sorted(baseline_dir.glob("*.png"))
        if len(generated_images) == 1 and len(baseline_images) == 1:
            generated_image = generated_images[0]
            baseline_name = baseline_images[0].name
            if generated_image.name != baseline_name:
                target_path = render_dir / baseline_name
                target_path.write_bytes(generated_image.read_bytes())
                generated_image.unlink()

        try:
            diff.compare_directories(render_dir, baseline_dir, diff_dir=diff_dir)
            logger.info("%s: diff clean", name)
        except ImageDiffError as exc:
            logger.error("%s: visual diff mismatch – %s", name, exc)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenarios", nargs="*", help="Scenario names to run")
    parser.add_argument(
        "--output",
        default="reports/visual/w3c",
        help="Directory to write generated artefacts",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if not args.verbose else logging.DEBUG)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_suite(args.scenarios, output_dir)


if __name__ == "__main__":
    main()
