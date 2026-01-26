#!/usr/bin/env python3
"""Compare sampled animation frames against golden snapshots using SSIM."""

import argparse
import logging
import sys
from pathlib import Path
from PIL import Image
import numpy as np
from skimage.metrics import structural_similarity as ssim

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("compare_frames")

def compare_frames(frames_dir: Path):
    if not frames_dir.exists():
        logger.error("Frames directory not found: %s", frames_dir)
        return

    # Find all golden frames
    golden_files = sorted(frames_dir.glob("golden_*.png"))
    
    print(f"{'Timestamp':<12} | {'SSIM Score':<10} | {'Status':<10}")
    print("-" * 40)

    for golden_path in golden_files:
        # Extract timestamp from filename like golden_1.0s.png
        timestamp_str = golden_path.stem.split("_")[1]
        
        # Look for corresponding converted render
        # Paths are like: .visual_tmp/animate_sample_frames/1.0s_render/animate_sample_1.0s.png
        render_subdirs = list(frames_dir.glob(f"{timestamp_str}_render"))
        if not render_subdirs:
            logger.warning("No render subdir found for %s", timestamp_str)
            continue
            
        render_dir = render_subdirs[0]
        # Look for slide_1.png (PowerPoint) first, then fallback to named file (LibreOffice)
        converted_files = list(render_dir.glob("slide_1.png"))
        if not converted_files:
            converted_files = list(render_dir.glob("*.png"))
            
        if not converted_files:
            logger.warning("No converted PNG found in %s", render_dir)
            continue
            
        converted_path = converted_files[0]
        
        # Load and compare
        img_golden = Image.open(golden_path).convert('L')
        img_converted = Image.open(converted_path).convert('L')
        
        # Ensure same size
        if img_golden.size != img_converted.size:
            img_converted = img_converted.resize(img_golden.size, Image.LANCZOS)
            
        arr_golden = np.array(img_golden)
        arr_converted = np.array(img_converted)
        
        mean_golden = np.mean(arr_golden) / 255.0
        mean_converted = np.mean(arr_converted) / 255.0
        
        score = ssim(arr_golden, arr_converted)
        status = "✅ PASS" if score > 0.95 else "❌ FAIL"
        
        print(f"{timestamp_str:<12} | {score:<10.4f} | {status:<10} | Mean(G): {mean_golden:.4f} Mean(C): {mean_converted:.4f}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Compare sampled frames.")
    parser.add_argument("dir", help="Directory containing frames to compare")
    args = parser.parse_args()
    compare_frames(Path(args.dir))
