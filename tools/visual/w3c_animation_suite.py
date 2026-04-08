#!/usr/bin/env python3
"""Run a W3C animation-focused SVG → PPTX comparison suite."""

from __future__ import annotations

from pathlib import Path

from tools.visual.suite_runner import run_cli

_INCLUDE_PATTERNS = (
    "animate-elem-*.svg",
    "animate-pservers-*.svg",
    "coords-transformattr-*.svg",
    "color-prop-*.svg",
)

_EXCLUDE_PREFIXES = (
    "animate-dom-",
    "animate-interact-",
    "animate-script-",
    "animate-struct-",
)


def _collect_scenarios() -> dict[str, Path]:
    root = Path("tests/svg")
    scenarios: dict[str, Path] = {}
    for pattern in _INCLUDE_PATTERNS:
        for path in sorted(root.glob(pattern)):
            stem = path.stem
            if stem.startswith(_EXCLUDE_PREFIXES):
                continue
            scenarios[stem] = path
    return scenarios


SCENARIOS = _collect_scenarios()


def main() -> None:
    run_cli(
        description=__doc__ or "Run the W3C animation visual comparison suite.",
        scenarios=SCENARIOS,
        golden_namespace="w3c-animation",
        default_output="reports/visual/w3c-animation",
    )


if __name__ == "__main__":
    main()
