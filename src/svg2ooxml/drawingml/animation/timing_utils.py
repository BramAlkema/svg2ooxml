"""Timing utilities for animation keyframe computation.

Provides:
- paced calcMode support via proportional keyTime distribution
- spline calcMode approximation by sampling dense linearized keyframes
"""

from __future__ import annotations

import math

from svg2ooxml.common.interpolation import InterpolationEngine
from svg2ooxml.ir.animation import TransformType

__all__ = [
    "compute_segment_durations_ms",
    "compute_paced_key_times",
    "compute_paced_key_times_2d",
    "sample_spline_keyframes",
]


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


def compute_segment_durations_ms(
    *,
    total_ms: int,
    n_values: int,
    key_times: list[float] | None = None,
) -> list[int]:
    """Return per-segment durations in milliseconds.

    When *key_times* are present they define the segment timing. Otherwise the
    duration is split evenly across ``n_values - 1`` segments with any rounding
    drift absorbed by the final segment.
    """
    if n_values <= 1:
        return [max(1, total_ms)]

    n_segments = n_values - 1
    if key_times is not None and len(key_times) == n_values:
        raw_durations = [
            max(1, int(round((key_times[index + 1] - key_times[index]) * total_ms)))
            for index in range(n_segments)
        ]
        covered_ms = int(
            round(
                max(0.0, min(1.0, key_times[-1])) * total_ms
                - max(0.0, min(1.0, key_times[0])) * total_ms
            )
        )
        drift = covered_ms - sum(raw_durations)
        raw_durations[-1] += drift
        raw_durations[-1] = max(1, raw_durations[-1])
        return raw_durations

    base = total_ms // n_segments
    segment_durations = [max(1, base)] * n_segments
    segment_durations[-1] += total_ms - sum(segment_durations)
    segment_durations[-1] = max(1, segment_durations[-1])
    return segment_durations


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


def sample_spline_keyframes(
    *,
    values: list[str],
    key_times: list[float] | None,
    key_splines: list[list[float]] | None,
    attribute_name: str,
    transform_type: TransformType | None = None,
    samples_per_segment: int = 8,
) -> tuple[list[str], list[float]]:
    """Approximate spline timing with explicit sampled keyframes."""
    if not values:
        return ([], [])

    resolved_times = (
        list(key_times)
        if key_times is not None and len(key_times) == len(values)
        else _uniform_key_times(len(values))
    )
    if len(values) <= 1 or not key_splines:
        return (list(values), resolved_times)

    interpolator = InterpolationEngine()
    sample_count = max(2, samples_per_segment)

    sampled_values = [values[0]]
    sampled_times = [resolved_times[0]]

    for index in range(len(values) - 1):
        start_time = resolved_times[index]
        end_time = resolved_times[index + 1]
        duration = end_time - start_time
        spline = key_splines[index] if index < len(key_splines) else None

        if spline is None or duration <= 0:
            sampled_values.append(values[index + 1])
            sampled_times.append(end_time)
            continue

        for step in range(1, sample_count + 1):
            local_progress = step / sample_count
            absolute_time = start_time + (duration * local_progress)
            interpolated = interpolator.interpolate_value(
                values[index],
                values[index + 1],
                local_progress,
                attribute_name,
                transform_type=transform_type,
                easing=spline,
            )
            sampled_values.append(interpolated.value)
            sampled_times.append(absolute_time)

    return _dedupe_adjacent_keyframes(sampled_values, sampled_times)


def _uniform_key_times(count: int) -> list[float]:
    if count <= 1:
        return [0.0]
    return [index / (count - 1) for index in range(count)]


def _dedupe_adjacent_keyframes(
    values: list[str],
    times: list[float],
) -> tuple[list[str], list[float]]:
    if not values or not times or len(values) != len(times):
        return (values, times)

    deduped_values = [values[0]]
    deduped_times = [times[0]]
    for value, time in zip(values[1:], times[1:], strict=True):
        if value == deduped_values[-1] and abs(time - deduped_times[-1]) <= 1e-9:
            continue
        deduped_values.append(value)
        deduped_times.append(time)
    return (deduped_values, deduped_times)
