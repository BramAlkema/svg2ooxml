#!/usr/bin/env python3
"""Build a single-slide PPTX with native DrawingML animations."""

import sys
import logging
from pathlib import Path
from lxml import etree

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("drawingml.writer").setLevel(logging.DEBUG)
logging.getLogger("drawingml.animation_writer").setLevel(logging.DEBUG)
logging.getLogger("drawingml.animation_pipeline").setLevel(logging.DEBUG)

# Add project root and src to path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from svg2ooxml.core.animation.parser import SMILParser
from svg2ooxml.ir.animation import AnimationType # Import AnimationType
from tools.visual.builder import PptxBuilder

def build_animated_pptx(svg_path: Path, output_pptx: Path, animation_types_filter: list[AnimationType] | None = None):
    svg_text = svg_path.read_text(encoding="utf-8")
    parser = etree.XMLParser(remove_blank_text=True)
    svg_root = etree.fromstring(svg_text.encode("utf-8"), parser)

    # 1. Parse animations
    smil_parser = SMILParser()
    all_animations = smil_parser.parse_svg_animations(svg_root)
    print(f"Found {len(all_animations)} animations")

    animations_to_build = []
    if animation_types_filter:
        for anim in all_animations:
            if anim.animation_type in animation_types_filter:
                animations_to_build.append(anim)
        print(f"Building {len(animations_to_build)} animations of types: {[a.name for a in animation_types_filter]}")
    else:
        animations_to_build = all_animations
        print(f"Building all {len(animations_to_build)} animations.")
    
    # 2. Build PPTX using native animation pipeline
    builder = PptxBuilder(slide_size_mode="same")
    
    # PptxBuilder.build_from_svg internal workflow:
    # 1. Parse SVG -> ParseResult (includes animations)
    # 2. Convert ParseResult -> IRScene
    # 3. Render IRScene -> DrawingML (DrawingMLWriter handles AnimationPipeline)
    # 4. Package DrawingML -> PPTX
    
    builder.build_from_svg(svg_text, output_pptx, source_path=svg_path, animations=animations_to_build)
    print(f"Built animated PPTX: {output_pptx}")

if __name__ == "__main__":
    svg_file = Path("tests/svg/animate-elem-24-t.svg")
    output_file = Path(".visual_tmp/native_animated_test_motion_only.pptx")
    build_animated_pptx(svg_file, output_file, animation_types_filter=[AnimationType.ANIMATE_MOTION])
