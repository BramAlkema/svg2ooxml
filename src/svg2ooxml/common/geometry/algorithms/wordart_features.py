"""Feature extraction for sampled WordArt text paths."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from svg2ooxml.common.geometry.points import dot_vectors, point_distance, vector_between
from svg2ooxml.common.math_utils import population_variance
from svg2ooxml.ir.text_path import PathPoint

from .wordart_types import PathFeatures

_COMMAND_RE = re.compile(r"[MmLlHhVvQqCcSsTtAaZz]")


def compute_features(
    points: Sequence[PathPoint], path_data: str | None
) -> PathFeatures:
    point_list = list(points)
    xs = [p.x for p in point_list]
    ys = [p.y for p in point_list]

    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    x_range = x_max - x_min
    y_range = y_max - y_min

    slope, intercept = linear_regression(xs, ys)
    slope_degrees = (
        math.degrees(math.atan(slope))
        if not math.isclose(slope, 0.0, abs_tol=1e-6)
        else 0.0
    )

    slopes = pairwise_slopes(xs, ys)
    curvature_sign_changes = count_sign_changes(slopes)

    peak_count, trough_count = count_extrema(ys)
    corner_count = count_corners(point_list)
    mean_y = sum(ys) / len(ys)
    zero_crossings = count_zero_crossings([y - mean_y for y in ys])

    command_counts = Counter[str]()
    if path_data:
        command_counts.update(cmd.upper() for cmd in _COMMAND_RE.findall(path_data))

    std_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys) / len(ys))

    return PathFeatures(
        is_closed=path_is_closed(point_list),
        point_count=len(point_list),
        x_range=x_range,
        y_range=y_range,
        slope=slope,
        intercept=intercept,
        slope_degrees=slope_degrees,
        curvature_sign_changes=curvature_sign_changes,
        peak_count=peak_count,
        trough_count=trough_count,
        corner_count=corner_count,
        zero_crossings=zero_crossings,
        arc_command_count=command_counts.get("A", 0),
        line_command_count=command_counts.get("L", 0),
        command_counts=command_counts,
        orientation=determine_orientation(point_list),
        amplitude=(y_range / 2) if ys else 0.0,
        mean_y=mean_y,
        std_y=std_y,
        x_variance=population_variance(xs),
        y_variance=population_variance(ys),
    )


def summarize_features(features: PathFeatures) -> dict[str, object]:
    return {
        "is_closed": features.is_closed,
        "point_count": features.point_count,
        "aspect_ratio": features.aspect_ratio(),
        "peak_count": features.peak_count,
        "trough_count": features.trough_count,
        "corner_count": features.corner_count,
        "orientation": features.orientation,
    }


def linear_regression(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
    n = len(xs)
    if n == 0:
        return 0.0, 0.0

    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys, strict=True))
    sum_x2 = sum(x * x for x in xs)

    denominator = n * sum_x2 - sum_x**2
    if abs(denominator) < 1e-12:
        return 0.0, sum_y / n if n > 0 else 0.0

    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n
    return slope, intercept


def pairwise_slopes(xs: Sequence[float], ys: Sequence[float]) -> list[float]:
    slopes: list[float] = []
    for index in range(1, len(xs)):
        dx = xs[index] - xs[index - 1]
        dy = ys[index] - ys[index - 1]
        slopes.append(float("inf") if abs(dx) < 1e-6 else dy / dx)
    return slopes


def count_sign_changes(values: Sequence[float]) -> int:
    count = 0
    prev_sign = None
    for value in values:
        if math.isinf(value):
            continue
        sign = 1 if value > 0 else -1 if value < 0 else 0
        if prev_sign is not None and sign != 0 and sign != prev_sign:
            count += 1
        if sign != 0:
            prev_sign = sign
    return count


def count_extrema(values: Sequence[float]) -> tuple[int, int]:
    peaks = 0
    troughs = 0
    for index in range(1, len(values) - 1):
        if values[index - 1] < values[index] > values[index + 1]:
            peaks += 1
        elif values[index - 1] > values[index] < values[index + 1]:
            troughs += 1
    return peaks, troughs


def count_corners(points: Sequence[PathPoint]) -> int:
    corners = 0
    for index in range(1, len(points) - 1):
        incoming = vector_between(points[index], points[index - 1])
        outgoing = vector_between(points[index + 1], points[index])
        mag_incoming = point_distance(points[index - 1], points[index])
        mag_outgoing = point_distance(points[index], points[index + 1])

        if mag_incoming * mag_outgoing == 0:
            continue

        cos_angle = dot_vectors(incoming, outgoing) / (mag_incoming * mag_outgoing)
        angle = math.degrees(math.acos(max(-1.0, min(1.0, cos_angle))))

        if angle < 120.0:
            corners += 1
    return corners


def count_zero_crossings(values: Sequence[float]) -> int:
    count = 0
    for index in range(1, len(values)):
        if values[index - 1] == 0 or values[index] == 0:
            continue
        if (values[index - 1] < 0 < values[index]) or (
            values[index - 1] > 0 > values[index]
        ):
            count += 1
    return count


def path_is_closed(points: Sequence[PathPoint]) -> bool:
    if not points:
        return False
    return point_distance(points[0], points[-1]) <= 1e-6


def determine_orientation(points: Sequence[PathPoint]) -> str:
    area = 0.0
    for index in range(len(points) - 1):
        area += (
            points[index].x * points[index + 1].y
            - points[index + 1].x * points[index].y
        )
    return "clockwise" if area < 0 else "counter_clockwise"


__all__ = [
    "compute_features",
    "count_corners",
    "count_extrema",
    "count_sign_changes",
    "count_zero_crossings",
    "determine_orientation",
    "linear_regression",
    "pairwise_slopes",
    "path_is_closed",
    "summarize_features",
]
