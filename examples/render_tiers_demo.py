"""Generate a four-tier PPTX demo from a sample SVG."""

from __future__ import annotations

import argparse
from pathlib import Path

from svg2ooxml.core.pptx_exporter import SvgPageSource, SvgToPptxExporter


def _default_svg() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    return repo_root / "tests" / "visual" / "fixtures" / "resvg" / "composite_filters.svg"


def _default_output() -> Path:
    return Path(__file__).resolve().parent / "tiered_demo.pptx"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render four fidelity tiers into a PPTX.")
    parser.add_argument(
        "svg",
        nargs="?",
        default=str(_default_svg()),
        help="Path to an SVG file (defaults to tests/visual/fixtures/resvg/composite_filters.svg).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(_default_output()),
        help="Output PPTX path (defaults to examples/tiered_demo.pptx).",
    )
    args = parser.parse_args()

    svg_path = Path(args.svg)
    if not svg_path.exists():
        raise SystemExit(f"SVG not found: {svg_path}")

    svg_text = svg_path.read_text(encoding="utf-8")
    output_path = Path(args.output)

    exporter = SvgToPptxExporter()
    page = SvgPageSource(
        svg_text=svg_text,
        title=svg_path.stem,
        name=svg_path.stem,
        metadata={"source": str(svg_path)},
    )
    result = exporter.convert_pages([page], output_path, render_tiers=True)

    print(f"Wrote {result.slide_count} slides to {output_path}")


if __name__ == "__main__":
    main()
