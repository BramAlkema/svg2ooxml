#!/usr/bin/env python3
import sys
from pathlib import Path

# Setup paths
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from tools.visual.builder import PptxBuilder
from tools.visual.renderer import default_renderer

def test_snapshot_build():
    snapshot_path = Path(".visual_tmp/animate_simple_frames/snapshot_0.0s.svg")
    if not snapshot_path.exists():
        print(f"Snapshot not found: {snapshot_path}")
        return
        
    svg = snapshot_path.read_text(encoding="utf-8")
    builder = PptxBuilder()
    output_pptx = Path(".visual_tmp/snapshot_test.pptx")
    builder.build_from_svg(svg, output_pptx)
    print(f"Built {output_pptx}")
    
    renderer = default_renderer()
    render_dir = Path(".visual_tmp/snapshot_render")
    renderer.render(output_pptx, render_dir)
    print(f"Rendered to {render_dir}")

if __name__ == "__main__":
    test_snapshot_build()
