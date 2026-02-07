"""Timing utilities for animation keyframe computation.

Provides paced calcMode support: distributing keyTimes proportionally
to inter-value distances so that velocity is constant.
"""

from __future__ import annotations

import math

__all__ = ["compute_paced_key_times", "compute_paced_key_times_2d"]


def compute_paced_key_times(values: list[float]) -> list[float] | None:
    """Compute paced keyTimes for 1D numeric values.

    Returns keyTimes proportional to cumulative distances between
    consecutive values.  Returns ``None`` if fewer than 2 values
    or total distance is zero (fallback to equal spacing).
    """
    if len(values) < 2:
        return None

    distances = [abs(values[i + 1] - values[i]) for i in range(len(values) - 1)]
    return _normalize_distances(distances, len(values))


def compute_paced_key_times_2d(
    pairs: list[tuple[float, float]],
) -> list[float] | None:
    """Compute paced keyTimes for 2D coordinate pairs.

    Uses Euclidean distance between consecutive points.
    Returns ``None`` if fewer than 2 pairs or total distance is zero.
    """
    if len(pairs) < 2:
        return None

    distances = [
        math.sqrt(
            (pairs[i + 1][0] - pairs[i][0]) ** 2
            + (pairs[i + 1][1] - pairs[i][1]) ** 2
        )
        for i in range(len(pairs) - 1)
    ]
    return _normalize_distances(distances, len(pairs))


def _normalize_distances(distances: list[float], n_values: int) -> list[float] | None:
    """Normalize segment distances to cumulative 0.0–1.0 keyTimes."""
    total = sum(distances)
    if total <= 0:
        return None  # Equal spacing fallback

    cumulative = [0.0]
    running = 0.0
    for d in distances:
        running += d
        cumulative.append(running / total)

    # Ensure exact 1.0 at the end
    cumulative[-1] = 1.0
    return cumulative
