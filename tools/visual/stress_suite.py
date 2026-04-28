#!/usr/bin/env python3
"""Run a curated set of non-W3C SVG stress comparisons."""

from __future__ import annotations

from pathlib import Path

from tools.visual.suite_runner import run_cli

_REQUIRED_SCENARIOS = {
    "gallardo": Path("tests/visual/fixtures/gallardo.svg"),
    "transform-torture": Path("tests/visual/fixtures/resvg/transform_torture.svg"),
    "sketch-illustration": Path(
        "tests/corpus/real_world/sketch_illustration_sample.svg"
    ),
    "figma-design-system": Path(
        "tests/corpus/real_world/figma_design_system_sample.svg"
    ),
}

_OPTIONAL_SCENARIOS = {
    "filter-turbulence": Path("tests/corpus/kelvin_lawrence/filter-turbulence.svg"),
    "filter-saturate": Path("tests/corpus/kelvin_lawrence/filter-saturate.svg"),
    "linear-gradients-repeat": Path(
        "tests/corpus/kelvin_lawrence/linear-gradients-repeat.svg"
    ),
    "mask-image": Path("tests/corpus/kelvin_lawrence/mask-image.svg"),
    "text-path": Path("tests/corpus/kelvin_lawrence/text-path.svg"),
    "text-path2": Path("tests/corpus/kelvin_lawrence/text-path2.svg"),
}

SCENARIOS = {
    **_REQUIRED_SCENARIOS,
    **{
        name: path
        for name, path in _OPTIONAL_SCENARIOS.items()
        if path.exists()
    },
}


def main() -> None:
    run_cli(
        description=__doc__ or "Run the non-W3C visual stress suite.",
        scenarios=SCENARIOS,
        golden_namespace="stress",
        default_output="reports/visual/stress",
    )


if __name__ == "__main__":
    main()
