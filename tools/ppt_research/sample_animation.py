#!/usr/bin/env python3
"""Sample an animated SVG at specific timestamps and build a PPTX with snapshots."""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

# Add project root and src to path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("sample_animation")

def validate_pptx(pptx_path: Path):
    """Validate PPTX using the SDK validator via Docker."""
    logger.info("Validating %s...", pptx_path.name)
    
    # Path relative to /Users/ynse/projects which is mapped to /work in docker
    # pptx_path is /Users/ynse/projects/svg2ooxml/.visual_tmp/...
    rel_path = pptx_path.resolve().relative_to(Path("/Users/ynse/projects"))
    docker_pptx_path = f"/work/{rel_path}"
    
    cmd = [
        "docker", "run", "--rm",
        "-v", "/Users/ynse/projects:/work",
        "-w", "/work/openxml-audit",
        "mcr.microsoft.com/dotnet/sdk:8.0",
        "dotnet", "run", "--project", "scripts/sdk_check/sdk_check.csproj", "--",
        docker_pptx_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            output = result.stdout.strip()
            if "Errors: 0" in output:
                logger.info("SDK Validation: PASS")
            else:
                logger.error("SDK Validation: FAIL\n%s", output)
        else:
            logger.error("SDK Validator crashed: %s", result.stderr)
    except Exception as e:
        logger.error("Failed to run validation: %s", e)

def generate_resvg_snapshot(svg_text: str, output_png: Path) -> None:
    """Render SVG text to a PNG using resvg-py."""
    try:
        from resvg_py import svg_to_bytes
        png_data = svg_to_bytes(svg_string=svg_text)
        if png_data:
            output_png.write_bytes(png_data)
            logger.info("Generated resvg snapshot: %s", output_png.name)
    except ImportError as e:
        logger.warning("resvg-py import failed: %s", e)
    except Exception as e:
        logger.error("resvg-py render failed: %s", e)
        import traceback
        traceback.print_exc()

def sample_svg(svg_path: Path, output_pptx: Path, timestamps: list[float]) -> None:
    """Sample SVG at timestamps and create a PPTX with one slide per sample."""
    from lxml import etree

    from svg2ooxml.core.animation.parser import SMILParser
    from svg2ooxml.core.animation.sampler import TimelineSampler
    from tools.visual.builder import PptxBuilder
    from tools.visual.renderer import default_renderer

    if not svg_path.exists():
        logger.error("SVG file not found: %s", svg_path)
        return

    svg_text = svg_path.read_text(encoding="utf-8")
    parser = etree.XMLParser(remove_blank_text=True)
    svg_root = etree.fromstring(svg_text.encode("utf-8"), parser)

    # 1. Parse animations
    smil_parser = SMILParser()
    animations = smil_parser.parse_svg_animations(svg_root)
    logger.info("Found %d animations in %s", len(animations), svg_path.name)

    # 2. Sample the timeline
    sampler = TimelineSampler()
    # We want specific timestamps
    snapshots = []
    for t in timestamps:
        # generate_scenes is a bit heavy, let's just manually generate scene at t
        scene = sampler._generate_scene_at_time(animations, t)
        snapshots.append(scene)

    # 3. Build and Render PPTX + resvg Snapshots
    builder = PptxBuilder(slide_size_mode="same")
    if sys.platform == "darwin":
        from tools.visual.renderer import PowerPointRenderer
        renderer = PowerPointRenderer()
    else:
        renderer = default_renderer()
    
    output_dir = output_pptx.parent / f"{output_pptx.stem}_frames"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for scene in snapshots:
        # Create a copy of the root to avoid corrupting it
        sample_root = etree.fromstring(etree.tostring(svg_root))
        
        # Apply scene state
        for element_id, properties in scene.element_states.items():
            elements = sample_root.xpath(f"//*[@id='{element_id}']")
            if not elements:
                logger.warning("Target element %s not found in snapshot %ss", element_id, scene.time)
            for el in elements:
                for attr, value in properties.items():
                    logger.info("Setting %s=%s on %s at t=%ss", attr, value, element_id, scene.time)
                    el.set(attr, str(value))
        
        sample_svg_text = etree.tostring(sample_root, encoding="unicode")
        
        # Save SVG for debugging
        sample_svg_path = output_dir / f"snapshot_{scene.time}s.svg"
        sample_svg_path.write_text(sample_svg_text, encoding="utf-8")
        logger.info("Saved SVG snapshot: %s", sample_svg_path.name)
        
        # A. Build PPTX
        sample_pptx = output_dir / f"{output_pptx.stem}_{scene.time}s.pptx"
        logger.info("Building PPTX for t=%ss -> %s", scene.time, sample_pptx.name)
        builder.build_from_svg(sample_svg_text, sample_pptx, source_path=svg_path)
        
        # B. Validate PPTX
        validate_pptx(sample_pptx)
        
        # C. Render PPTX PNG
        if renderer.available:
            render_dir = output_dir / f"{scene.time}s_render"
            logger.info("Rendering converted PNG for t=%ss -> %s", scene.time, render_dir)
            renderer.render(sample_pptx, render_dir)
        else:
            logger.warning("Renderer not available; skipping PNG generation.")
        
        # D. Render resvg Golden PNG
        golden_png = output_dir / f"golden_{scene.time}s.png"
        generate_resvg_snapshot(sample_svg_text, golden_png)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("svg", help="Path to animated SVG file")
    parser.add_argument("--times", nargs="+", type=float, default=[0.0, 1.0, 2.0, 3.0, 4.0], help="Timestamps to sample")
    parser.add_argument("-o", "--output", default="sampled_animation.pptx", help="Base name for output PPTX files")
    
    args = parser.parse_args()
    
    sample_svg(Path(args.svg), Path(args.output), args.times)

if __name__ == "__main__":
    main()
