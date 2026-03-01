
#!/usr/bin/env python3
"""Create a single PPTX presentation containing all W3C test scenarios found in tests/svg."""

from __future__ import annotations

import logging
import argparse
from pathlib import Path
from typing import List

from svg2ooxml.core.pptx_exporter import SvgPageSource, SvgToPptxExporter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("w3c_summary")

def main() -> None:
    parser = argparse.ArgumentParser(description="Create a summary PPTX of W3C tests.")
    parser.add_argument("--limit", type=int, help="Limit the number of tests.")
    parser.add_argument("--pattern", type=str, default="*.svg", help="Pattern to match SVG files.")
    parser.add_argument("--output", type=str, default="reports/w3c_comprehensive_summary.pptx", help="Output PPTX path.")
    args = parser.parse_args()

    svg_dir = Path("tests/svg")
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    svg_files = sorted(list(svg_dir.glob(args.pattern)))
    if args.limit:
        svg_files = svg_files[:args.limit]

    pages: List[SvgPageSource] = []
    
    for svg_path in svg_files:
        logger.info(f"Adding scenario: {svg_path.name}")
        try:
            svg_text = svg_path.read_text(encoding="utf-8")
            
            # We pass source_path in metadata so the parser can resolve relative images
            page = SvgPageSource(
                svg_text=svg_text,
                title=svg_path.stem,
                name=svg_path.stem,
                metadata={"source_path": str(svg_path.resolve())}
            )
            pages.append(page)
        except Exception as e:
            logger.warning(f"Failed to read {svg_path}: {e}")

    if not pages:
        logger.error("No valid scenarios found.")
        return

    # Use 'same' slide size mode to keep original SVG dimensions per slide
    exporter = SvgToPptxExporter(slide_size_mode="same")
    
    logger.info(f"Generating PPTX with {len(pages)} slides...")
    try:
        result = exporter.convert_pages(
            pages=pages,
            output_path=output_path,
            render_tiers=False,
            parallel=True,
        )
        logger.info(f"Successfully created {output_path} with {result.slide_count} slides.")
    except Exception as exc:
        logger.error(f"Failed to generate PPTX: {exc}", exc_info=True)

if __name__ == "__main__":
    main()
