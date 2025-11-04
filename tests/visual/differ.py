"""Visual differ tool for comparing rendered images.

This module provides SSIM-based image comparison for visual regression testing.
It uses scikit-image's structural similarity index to detect visual differences
and can generate diff images highlighting changed regions.

Example:
    from tests.visual.differ import VisualDiffer
    from PIL import Image

    differ = VisualDiffer(threshold=0.95)
    baseline = Image.open("baseline.png")
    actual = Image.open("actual.png")
    
    result = differ.compare(baseline, actual)
    print(f"SSIM: {result.ssim_score:.4f}")
    print(f"Passed: {result.passed}")
    print(f"Pixel diff: {result.pixel_diff_percentage:.2f}%")
    
    if not result.passed:
        result.save_diff("diff.png")
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim


@dataclass
class DiffResult:
    """Result of visual comparison between two images.
    
    Attributes:
        ssim_score: Structural similarity index (0.0-1.0, higher is more similar)
        pixel_diff_percentage: Percentage of pixels that differ (0.0-100.0)
        passed: Whether the comparison passed the threshold
        threshold: SSIM threshold used for pass/fail (0.0-1.0)
        diff_image: Optional PIL Image highlighting differences (red overlay)
        baseline_shape: Shape of baseline image (width, height, channels)
        actual_shape: Shape of actual image (width, height, channels)
    """
    
    ssim_score: float
    pixel_diff_percentage: float
    passed: bool
    threshold: float
    diff_image: Optional[Image.Image] = None
    baseline_shape: Optional[Tuple[int, int, int]] = None
    actual_shape: Optional[Tuple[int, int, int]] = None
    
    def save_diff(self, path: str | Path) -> None:
        """Save diff image to file.
        
        Args:
            path: Output path for diff image
            
        Raises:
            ValueError: If no diff image is available
        """
        if self.diff_image is None:
            raise ValueError("No diff image available (set generate_diff=True)")
        self.diff_image.save(str(path))


class VisualDiffer:
    """Image comparison tool using SSIM (Structural Similarity Index).
    
    This class provides methods to compare images and detect visual differences
    using SSIM, which correlates well with human perception of image quality.
    
    Args:
        threshold: SSIM threshold for pass/fail (default: 0.95)
        pixel_diff_threshold: Pixel difference threshold in [0, 255] (default: 10)
        
    Example:
        differ = VisualDiffer(threshold=0.98)
        result = differ.compare(baseline, actual, generate_diff=True)
        if not result.passed:
            print(f"Failed with SSIM {result.ssim_score:.4f}")
            result.save_diff("failure.png")
    """
    
    def __init__(
        self,
        threshold: float = 0.95,
        pixel_diff_threshold: int = 10,
    ):
        """Initialize VisualDiffer.
        
        Args:
            threshold: SSIM threshold for pass/fail (0.0-1.0)
            pixel_diff_threshold: Pixel value difference threshold (0-255)
            
        Raises:
            ValueError: If threshold not in [0.0, 1.0] or pixel_diff_threshold not in [0, 255]
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"threshold must be in [0.0, 1.0], got {threshold}")
        if not 0 <= pixel_diff_threshold <= 255:
            raise ValueError(
                f"pixel_diff_threshold must be in [0, 255], got {pixel_diff_threshold}"
            )
        
        self.threshold = threshold
        self.pixel_diff_threshold = pixel_diff_threshold
    
    def compare(
        self,
        baseline: Image.Image,
        actual: Image.Image,
        generate_diff: bool = True,
    ) -> DiffResult:
        """Compare two images and return similarity metrics.
        
        This method converts images to numpy arrays, computes SSIM, and optionally
        generates a diff image highlighting changed regions in red.
        
        Args:
            baseline: Baseline/expected image
            actual: Actual/test image
            generate_diff: Whether to generate diff visualization (default: True)
            
        Returns:
            DiffResult with SSIM score, pixel diff percentage, and optional diff image
            
        Raises:
            ValueError: If images have different sizes
        """
        # Convert to RGB if needed (handle RGBA, grayscale, etc.)
        baseline_rgb = baseline.convert("RGB")
        actual_rgb = actual.convert("RGB")
        
        # Convert to numpy arrays
        baseline_arr = np.array(baseline_rgb)
        actual_arr = np.array(actual_rgb)
        
        # Check dimensions match
        if baseline_arr.shape != actual_arr.shape:
            raise ValueError(
                f"Image shapes don't match: baseline {baseline_arr.shape} "
                f"vs actual {actual_arr.shape}"
            )
        
        # Compute SSIM
        # SSIM expects channel_axis=2 for RGB images (H, W, C)
        # data_range is max pixel value (255 for uint8)
        # win_size must be odd and <= min(height, width)
        # For very small images (<3x3), SSIM doesn't work well, so fallback to simple comparison
        h, w = baseline_arr.shape[:2]
        min_dim = min(h, w)

        if min_dim < 3:
            # For very small images, use simple pixel-wise comparison
            # SSIM = 1.0 if identical, 0.0 if completely different
            ssim_score = 1.0 if np.array_equal(baseline_arr, actual_arr) else 0.0
            # Create a dummy SSIM map (all 1.0 if equal, all 0.0 if different)
            ssim_map = np.full((h, w, 3), ssim_score, dtype=np.float64)
        else:
            # Use proper SSIM for larger images
            win_size = min(7, min_dim if min_dim % 2 == 1 else min_dim - 1)

            ssim_score, ssim_map = ssim(
                baseline_arr,
                actual_arr,
                channel_axis=2,
                data_range=255,
                win_size=win_size,
                full=True,
            )
        
        # Compute pixel diff percentage
        pixel_diff_pct = self._compute_pixel_diff_percentage(baseline_arr, actual_arr)
        
        # Generate diff image if requested
        diff_image = None
        if generate_diff:
            diff_image = self._generate_diff_image(baseline_arr, actual_arr, ssim_map)
        
        # Determine pass/fail (convert to Python bool to avoid numpy bool)
        passed = bool(ssim_score >= self.threshold)

        return DiffResult(
            ssim_score=float(ssim_score),
            pixel_diff_percentage=float(pixel_diff_pct),
            passed=passed,
            threshold=self.threshold,
            diff_image=diff_image,
            baseline_shape=baseline_arr.shape,
            actual_shape=actual_arr.shape,
        )
    
    def _compute_pixel_diff_percentage(
        self,
        baseline: np.ndarray,
        actual: np.ndarray,
    ) -> float:
        """Compute percentage of pixels that differ beyond threshold.
        
        Args:
            baseline: Baseline image array (H, W, C)
            actual: Actual image array (H, W, C)
            
        Returns:
            Percentage of differing pixels (0.0-100.0)
        """
        # Compute absolute difference per channel
        diff = np.abs(baseline.astype(np.int16) - actual.astype(np.int16))
        
        # A pixel "differs" if ANY channel exceeds threshold
        diff_pixels = np.any(diff > self.pixel_diff_threshold, axis=2)
        
        # Count differing pixels
        num_diff = np.sum(diff_pixels)
        total_pixels = diff_pixels.shape[0] * diff_pixels.shape[1]
        
        return (num_diff / total_pixels) * 100.0
    
    def _generate_diff_image(
        self,
        baseline: np.ndarray,
        actual: np.ndarray,
        ssim_map: np.ndarray,
    ) -> Image.Image:
        """Generate diff image with red overlay on changed regions.

        Args:
            baseline: Baseline image array (H, W, C)
            actual: Actual image array (H, W, C)
            ssim_map: SSIM similarity map (H, W, C) with values in [0, 1] per channel

        Returns:
            PIL Image with red overlay on differences
        """
        # Start with the actual image
        diff_img = actual.copy()

        # SSIM map has shape (H, W, C) with per-channel similarity
        # Compute minimum similarity across channels for conservative masking
        # (a pixel is "different" if ANY channel has low SSIM)
        if ssim_map.ndim == 3:
            ssim_min = np.min(ssim_map, axis=2)  # (H, W)
        else:
            ssim_min = ssim_map  # Already 2D

        # Threshold at 0.95 for diff visualization
        diff_threshold = 0.95
        low_ssim_mask = ssim_min < diff_threshold

        # Only apply overlay if there are any differences
        if np.any(low_ssim_mask):
            # Create red overlay (bright red) on all 3 channels
            diff_img[low_ssim_mask, :] = [255, 0, 0]

        # Convert back to PIL Image
        return Image.fromarray(diff_img.astype(np.uint8))


__all__ = ["VisualDiffer", "DiffResult"]
