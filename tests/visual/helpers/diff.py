"""Utilities for comparing rendered slide images during visual tests."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from PIL import Image, ImageChops, ImageStat  # type: ignore[import]

logger = logging.getLogger(__name__)


class ImageDiffError(AssertionError):
    """Raised when two image directories differ beyond the accepted tolerance."""


@dataclass
class DiffResult:
    """Description of a diff run."""

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
    ) -> DiffResult:
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
                # Optionally keep diff artifacts for inspection even on success.
                diff_path = diff_dir / f"{Path(name).stem}_diff.png"
                diff_image.save(diff_path)
                diff_paths.append(diff_path)

        logger.debug(
            "Compared %d slide image(s) – worst max delta %.2f, mean delta %.2f",
            len(baseline_map),
            worst_max,
            worst_mean,
        )

        return DiffResult(
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
            raise ImageDiffError(
                f"Image sizes differ (generated {candidate.size}, baseline {baseline.size})."
            )

        diff = ImageChops.difference(candidate, baseline)
        stat = ImageStat.Stat(diff)

        max_delta = max(extreme[1] for extreme in stat.extrema)
        mean_delta = max(stat.mean)

        # Highlight differences by tinting them red for easier inspection.
        mask = diff.convert("L")
        if mask.getbbox() is None:
            highlight = Image.new("RGBA", diff.size, (0, 0, 0, 0))
        else:
            alpha = mask.point(lambda value: 0 if value == 0 else max(96, min(255, value)))
            highlight = Image.new("RGBA", diff.size, (255, 0, 0, 0))
            highlight.putalpha(alpha)

        return max_delta, mean_delta, highlight


__all__ = ["ImageDiff", "ImageDiffError", "DiffResult"]
