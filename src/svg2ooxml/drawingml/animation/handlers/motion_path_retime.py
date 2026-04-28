"""Timing-aware retiming and sampling for motion path points."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from svg2ooxml.drawingml.animation.handlers.motion_path_types import PointPair
from svg2ooxml.drawingml.animation.timing_utils import compute_paced_key_times_2d
from svg2ooxml.ir.animation import CalcMode

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition


def retime_motion_points(
    points: list[PointPair],
    animation: AnimationDefinition,
    segment_budget: int = 96,
) -> list[PointPair]:
    """Approximate keyTimes/calcMode timing by expanding path vertices."""

    if len(points) < 2:
        return points

    calc_mode_value = (
        animation.calc_mode.value
        if isinstance(animation.calc_mode, CalcMode)
        else str(animation.calc_mode).lower()
    )
    key_points, key_times = _resolve_retime_anchors(points, animation, calc_mode_value)
    if len(key_points) < 2 or len(key_times) != len(key_points):
        return points

    if calc_mode_value == CalcMode.DISCRETE.value:
        return expand_discrete_points(
            points=key_points,
            key_times=key_times,
            segment_budget=segment_budget,
        )
    return retime_linear_points(
        points=key_points,
        key_times=key_times,
        segment_budget=segment_budget,
    )


def _resolve_retime_anchors(
    points: list[PointPair],
    animation: AnimationDefinition,
    calc_mode_value: str,
) -> tuple[list[PointPair], list[float]]:
    if animation.key_points is not None and len(animation.key_points) >= 2:
        key_points = sample_points_at_progress(points, animation.key_points)
        if (
            animation.key_times is not None
            and len(animation.key_times) == len(animation.key_points)
        ):
            return key_points, list(animation.key_times)
        return key_points, uniform_key_times(len(key_points))

    if calc_mode_value == CalcMode.PACED.value:
        if len(points) < 3 and not animation.key_times:
            return points, []
        key_points = list(points)
        paced_times = compute_paced_key_times_2d(key_points)
        return key_points, paced_times or uniform_key_times(len(key_points))

    if animation.key_times is not None and len(animation.key_times) >= 2:
        key_times = list(animation.key_times)
        key_points = (
            list(points)
            if len(key_times) == len(points)
            else sample_points_at_progress(points, key_times)
        )
        return key_points, key_times

    if calc_mode_value in {
        CalcMode.LINEAR.value,
        CalcMode.DISCRETE.value,
    } and len(points) > 2:
        key_points = list(points)
        return key_points, uniform_key_times(len(key_points))

    return points, []


def uniform_key_times(count: int) -> list[float]:
    if count <= 1:
        return [0.0]
    return [index / (count - 1) for index in range(count)]


def sample_points_at_progress(
    points: list[PointPair],
    key_times: list[float],
) -> list[PointPair]:
    if len(points) < 2 or len(key_times) < 2:
        return points

    lengths = [0.0]
    total = 0.0
    for index in range(1, len(points)):
        x0, y0 = points[index - 1]
        x1, y1 = points[index]
        total += math.hypot(x1 - x0, y1 - y0)
        lengths.append(total)

    if total <= 1e-9:
        return [points[0] for _ in key_times]

    sampled: list[PointPair] = []
    for fraction in key_times:
        target = max(0.0, min(1.0, fraction)) * total
        sampled.append(
            sample_polyline_at_distance(
                points=points,
                cumulative_lengths=lengths,
                target_distance=target,
            )
        )
    return sampled


def sample_polyline_at_distance(
    *,
    points: list[PointPair],
    cumulative_lengths: list[float],
    target_distance: float,
) -> PointPair:
    if target_distance <= 0.0:
        return points[0]
    if target_distance >= cumulative_lengths[-1]:
        return points[-1]

    for index in range(1, len(points)):
        prev_dist = cumulative_lengths[index - 1]
        curr_dist = cumulative_lengths[index]
        if target_distance <= curr_dist:
            span = curr_dist - prev_dist
            if span <= 1e-9:
                return points[index]
            t = (target_distance - prev_dist) / span
            x0, y0 = points[index - 1]
            x1, y1 = points[index]
            return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)

    return points[-1]


def retime_linear_points(
    *,
    points: list[PointPair],
    key_times: list[float],
    segment_budget: int,
) -> list[PointPair]:
    expanded: list[PointPair] = [points[0]]
    for index in range(1, len(points)):
        start = points[index - 1]
        end = points[index]
        duration = max(0.0, key_times[index] - key_times[index - 1])
        segment_count = max(1, int(round(duration * segment_budget)))

        for step in range(1, segment_count + 1):
            t = step / segment_count
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            expanded.append((x, y))

    return expanded


def expand_discrete_points(
    *,
    points: list[PointPair],
    key_times: list[float],
    segment_budget: int,
) -> list[PointPair]:
    expanded: list[PointPair] = [points[0]]
    for index in range(1, len(points)):
        prev = points[index - 1]
        curr = points[index]
        duration = max(0.0, key_times[index] - key_times[index - 1])
        slot_count = max(1, int(round(duration * segment_budget)))

        for _ in range(max(0, slot_count - 1)):
            expanded.append(prev)
        expanded.append(curr)

    return expanded


__all__ = [
    "expand_discrete_points",
    "retime_linear_points",
    "retime_motion_points",
    "sample_points_at_progress",
    "sample_polyline_at_distance",
    "uniform_key_times",
]
