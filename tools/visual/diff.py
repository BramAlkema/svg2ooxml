"""Visual diff helpers for image comparisons."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageStat

try:  # pragma: no cover - optional dependency
    from skimage.metrics import structural_similarity as _ssim_impl
except ImportError:  # pragma: no cover - handled at runtime
    _ssim_impl = None


class ImageDiffError(AssertionError):
    """Raised when two image directories differ beyond the accepted tolerance."""


@dataclass
class ImageDiffResult:
    """Description of a directory diff run."""

    compared: int
    max_delta: float
    mean_delta: float
    diff_images: Sequence[Path]


class ImageDiff:
    """Compute per-pixel differences between PNG directories."""

    def __init__(
        self,
        *,
        max_delta: float = 12.0,
        mean_delta: float = 1.5,
    ) -> None:
        self.max_delta = max_delta
        self.mean_delta = mean_delta

    def compare_directories(
        self,
        generated_dir: Path,
        baseline_dir: Path,
        *,
        diff_dir: Path | None = None,
    ) -> ImageDiffResult:
        """Compare PNG images in *generated_dir* with *baseline_dir*."""

        generated_dir = Path(generated_dir)
        baseline_dir = Path(baseline_dir)

        if not baseline_dir.exists():
            raise ImageDiffError(f"Baseline directory does not exist: {baseline_dir}")
        if not generated_dir.exists():
            raise ImageDiffError(f"Generated directory does not exist: {generated_dir}")

        generated_map = {path.name: path for path in generated_dir.glob("*.png")}
        baseline_map = {path.name: path for path in baseline_dir.glob("*.png")}

        missing = sorted(set(baseline_map) - set(generated_map))
        if missing:
            raise ImageDiffError(f"Generated output is missing slide(s): {', '.join(missing)}")

        diff_paths: List[Path] = []
        worst_max = 0.0
        worst_mean = 0.0

        if diff_dir is not None:
            diff_dir = Path(diff_dir)
            diff_dir.mkdir(parents=True, exist_ok=True)

        for name in sorted(baseline_map):
            baseline_image = Image.open(baseline_map[name]).convert("RGBA")
            candidate_image = Image.open(generated_map[name]).convert("RGBA")
            max_delta, mean_delta, diff_image = self._compare_images(candidate_image, baseline_image)

            worst_max = max(worst_max, max_delta)
            worst_mean = max(worst_mean, mean_delta)

            if max_delta > self.max_delta or mean_delta > self.mean_delta:
                if diff_dir is not None:
                    diff_path = diff_dir / f"{Path(name).stem}_diff.png"
                    diff_image.save(diff_path)
                    diff_paths.append(diff_path)
                message = (
                    f"Slide {name} exceeded tolerance "
                    f"(max delta {max_delta:.2f} vs {self.max_delta}, "
                    f"mean delta {mean_delta:.2f} vs {self.mean_delta})."
                )
                raise ImageDiffError(message)

            if diff_dir is not None:
                diff_path = diff_dir / f"{Path(name).stem}_diff.png"
                diff_image.save(diff_path)
                diff_paths.append(diff_path)

        return ImageDiffResult(
            compared=len(baseline_map),
            max_delta=worst_max,
            mean_delta=worst_mean,
            diff_images=tuple(diff_paths),
        )

    def _compare_images(
        self,
        candidate: Image.Image,
        baseline: Image.Image,
    ) -> tuple[float, float, Image.Image]:
        if candidate.size != baseline.size:
            candidate = _resize_to_match(candidate, baseline)

        diff = ImageChops.difference(candidate, baseline)
        stat = ImageStat.Stat(diff)

        max_delta = max(extreme[1] for extreme in stat.extrema)
        mean_delta = max(stat.mean)

        mask = diff.convert("L")
        if mask.getbbox() is None:
            highlight = Image.new("RGBA", diff.size, (0, 0, 0, 0))
        else:
            alpha = mask.point(lambda value: 0 if value == 0 else max(96, min(255, value)))
            highlight = Image.new("RGBA", diff.size, (255, 0, 0, 0))
            highlight.putalpha(alpha)

        return max_delta, mean_delta, highlight


@dataclass
class DiffResult:
    """Result of SSIM-based image comparison."""

    ssim_score: float
    pixel_diff_percentage: float
    passed: bool
    threshold: float
    diff_image: Optional[Image.Image] = None
    baseline_shape: Optional[Tuple[int, int, int]] = None
    actual_shape: Optional[Tuple[int, int, int]] = None

    def save_diff(self, path: str | Path) -> None:
        if self.diff_image is None:
            raise ValueError("No diff image available (set generate_diff=True)")
        self.diff_image.save(str(path))


class VisualDiffer:
    """Image comparison tool using SSIM."""

    def __init__(
        self,
        threshold: float = 0.95,
        pixel_diff_threshold: int = 10,
    ) -> None:
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
        baseline_rgb = baseline.convert("RGB")
        actual_rgb = actual.convert("RGB")

        if baseline_rgb.size != actual_rgb.size:
            actual_rgb = _resize_to_match(actual_rgb, baseline_rgb)

        baseline_arr = np.array(baseline_rgb)
        actual_arr = np.array(actual_rgb)

        h, w = baseline_arr.shape[:2]
        min_dim = min(h, w)

        if min_dim < 3:
            ssim_score = 1.0 if np.array_equal(baseline_arr, actual_arr) else 0.0
            ssim_map = np.full((h, w, 3), ssim_score, dtype=np.float64)
        else:
            if _ssim_impl is None:
                raise RuntimeError(
                    "scikit-image is required for VisualDiffer.compare(); "
                    "install via 'pip install scikit-image' to enable visual comparisons."
                )

            win_size = min(7, min_dim if min_dim % 2 == 1 else min_dim - 1)

            ssim_score, ssim_map = _ssim_impl(
                baseline_arr,
                actual_arr,
                channel_axis=2,
                data_range=255,
                win_size=win_size,
                full=True,
            )

        pixel_diff_pct = self._compute_pixel_diff_percentage(baseline_arr, actual_arr)

        diff_image = None
        if generate_diff:
            diff_image = self._generate_diff_image(baseline_arr, actual_arr, ssim_map)

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
        diff = np.abs(baseline.astype(np.int16) - actual.astype(np.int16))
        mask = np.any(diff > self.pixel_diff_threshold, axis=2)
        diff_pixels = np.count_nonzero(mask)
        total_pixels = baseline.shape[0] * baseline.shape[1]
        return (diff_pixels / total_pixels) * 100.0 if total_pixels else 0.0

    def _generate_diff_image(
        self,
        baseline: np.ndarray,
        actual: np.ndarray,
        ssim_map: np.ndarray,
    ) -> Image.Image:
        diff_mask = (ssim_map < 1.0).any(axis=2)
        diff_overlay = np.zeros_like(baseline)
        diff_overlay[:, :, 0] = 255
        alpha = np.where(diff_mask, 128, 0).astype(np.uint8)

        base = Image.fromarray(actual.astype(np.uint8))
        overlay = Image.fromarray(diff_overlay.astype(np.uint8))
        overlay.putalpha(Image.fromarray(alpha))
        base.paste(overlay, (0, 0), overlay)
        return base


def _resize_to_match(actual: Image.Image, baseline: Image.Image) -> Image.Image:
    ratio_actual = actual.width / actual.height
    ratio_baseline = baseline.width / baseline.height
    if abs(ratio_actual - ratio_baseline) > 0.01:
        raise ImageDiffError(
            f"Image sizes differ (generated {actual.size}, baseline {baseline.size})."
        )
    resample = getattr(Image, "Resampling", Image).LANCZOS
    return actual.resize(baseline.size, resample=resample)


__all__ = [
    "DiffResult",
    "ImageDiff",
    "ImageDiffError",
    "ImageDiffResult",
    "VisualDiffer",
]
