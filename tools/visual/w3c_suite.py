#!/usr/bin/env python3
"""Run a curated set of SVG → PPTX comparisons for W3C fixtures."""

from __future__ import annotations

from pathlib import Path

from tools.visual.suite_runner import run_cli


SCENARIOS = {
    "struct-use-10-f": Path("tests/svg/struct-use-10-f.svg"),
    "struct-use-11-f": Path("tests/svg/struct-use-11-f.svg"),
    "styling-css-01-b": Path("tests/svg/styling-css-01-b.svg"),
    "text-tspan-01-b": Path("tests/svg/text-tspan-01-b.svg"),
    "filters-gauss-01-b": Path("tests/svg/filters-gauss-01-b.svg"),
    "filters-diffuse-01-f": Path("tests/svg/filters-diffuse-01-f.svg"),
    "filters-specular-01-f": Path("tests/svg/filters-specular-01-f.svg"),
    "filters-light-01-f": Path("tests/svg/filters-light-01-f.svg"),
    "filters-light-02-f": Path("tests/svg/filters-light-02-f.svg"),
    "coords-trans-09-t": Path("tests/svg/coords-trans-09-t.svg"),
    "simple-rect": Path("tests/visual/fixtures/simple_rect.svg"),
    "pattern-tile-transforms": Path(
        "tests/visual/fixtures/resvg/pattern_tile_transforms.svg"
    ),
}


def main() -> None:
    run_cli(
        description=__doc__ or "Run the W3C visual comparison suite.",
        scenarios=SCENARIOS,
        golden_namespace="w3c",
        default_output="reports/visual/w3c",
    )


if __name__ == "__main__":
    main()
