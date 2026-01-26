#!/usr/bin/env python3
import sys
from pathlib import Path

# Setup paths
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from tools.visual.builder import PptxBuilder
from tools.visual.renderer import default_renderer

def test_static_build():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360"><rect x="0" y="0" width="100" height="100" fill="red" /></svg>'
    builder = PptxBuilder()
    output_pptx = Path(".visual_tmp/static_test.pptx")
    builder.build_from_svg(svg, output_pptx)
    print(f"Built {output_pptx}")
    
    renderer = default_renderer()
    render_dir = Path(".visual_tmp/static_render")
    renderer.render(output_pptx, render_dir)
    print(f"Rendered to {render_dir}")

if __name__ == "__main__":
    test_static_build()
