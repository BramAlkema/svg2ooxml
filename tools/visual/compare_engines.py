#!/usr/bin/env python3
"""Compare resvg and legacy engines side-by-side for a given SVG."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from tools.visual.builder import PptxBuilder
from tools.visual.renderer import default_renderer
from tools.visual.diff import VisualDiffer
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("compare_engines")

def compare_svg(svg_path: Path, output_dir: Path):
    svg_path = Path(svg_path)
    svg_text = svg_path.read_text(encoding="utf-8")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    renderer = default_renderer()
    if not renderer.available:
        raise SystemExit("LibreOffice (soffice) is not available.")
    
    modes = ["resvg", "legacy"]
    results = {}
    
    for mode in modes:
        mode_dir = output_dir / mode
        mode_dir.mkdir(exist_ok=True)
        
        logger.info(f"Building PPTX with {mode} engine...")
        builder = PptxBuilder(filter_strategy=mode, geometry_mode=mode)
        pptx_path = mode_dir / "presentation.pptx"
        builder.build_from_svg(svg_text, pptx_path, source_path=svg_path)
        
        logger.info(f"Rendering {mode} PPTX...")
        render_dir = mode_dir / "render"
        render_dir.mkdir(exist_ok=True)
        slide_set = renderer.render(pptx_path, render_dir)
        
        if slide_set.images:
            results[mode] = Path(slide_set.images[0])
            logger.info(f"{mode} render complete: {results[mode]}")
    
    if len(results) == 2:
        logger.info("Computing diff between resvg and legacy...")
        img_resvg = Image.open(results["resvg"])
        img_legacy = Image.open(results["legacy"])
        
        differ = VisualDiffer(threshold=0.95)
        diff_result = differ.compare(img_legacy, img_resvg, generate_diff=True)
        
        diff_path = output_dir / "engines_diff.png"
        if diff_result.diff_image:
            diff_result.diff_image.save(diff_path)
            logger.info(f"Diff saved to: {diff_path}")
        
        logger.info(f"SSIM Score: {diff_result.ssim_score:.4f}")
        logger.info(f"Pixel Diff: {diff_result.pixel_diff_percentage:.2f}%")
        if diff_result.passed:
            logger.info("✅ Engines are visually equivalent (within threshold)")
        else:
            logger.info("⚠️ Engines diverge significantly")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("svg", help="Path to SVG file")
    parser.add_argument("--output", default="reports/visual/comparison", help="Output directory")
    args = parser.parse_args()
    
    compare_svg(Path(args.svg), Path(args.output))

if __name__ == "__main__":
    main()
