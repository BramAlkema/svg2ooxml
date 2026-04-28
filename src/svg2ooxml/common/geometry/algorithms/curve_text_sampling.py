"""Path sampling helpers for curve text positioning."""

from __future__ import annotations

import math

from svg2ooxml.common.geometry.algorithms.curve_text_types import PathSegment
from svg2ooxml.ir.text_path import PathPoint


def fallback_horizontal_line(num_samples: int) -> list[PathPoint]:
    """Generate fallback horizontal line when path parsing fails."""
    points = []
    for i in range(num_samples):
        x = 100.0 * i / max(1, num_samples - 1)
        points.append(
            PathPoint(
                x=x,
                y=0.0,
                tangent_angle=0.0,
                distance_along_path=x,
            )
        )
    return points


def sample_path_deterministic(
    segments: list[PathSegment],
    total_length: float,
    num_samples: int,
) -> list[PathPoint]:
    """
    Deterministic equal arc-length sampling with contract guarantees.

    Contract:
    - Returns exactly num_samples points
    - Monotonic distance_along_path
    - Equal spacing by arc length
    """
    cumulative_lengths = [0.0]
    for segment in segments:
        cumulative_lengths.append(cumulative_lengths[-1] + segment.length)

    path_points = []

    for i in range(num_samples):
        s_target = (total_length * i) / (num_samples - 1) if num_samples > 1 else 0

        seg_idx = 0
        for j in range(len(cumulative_lengths) - 1):
            if cumulative_lengths[j] <= s_target <= cumulative_lengths[j + 1]:
                seg_idx = j
                break

        s_local = s_target - cumulative_lengths[seg_idx]
        segment = segments[seg_idx]

        path_points.append(sample_segment_at_distance(segment, s_local, s_target))

    return path_points


def sample_path_proportional(
    segments: list[PathSegment],
    total_length: float,
    num_samples: int,
) -> list[PathPoint]:
    """Legacy proportional sampling method."""
    path_points = []
    cumulative_distance = 0.0

    for segment in segments:
        segment_ratio = segment.length / total_length if total_length > 0 else 0
        segment_samples = max(2, int(num_samples * segment_ratio))
        segment_points = sample_segment(segment, segment_samples, cumulative_distance)

        if not path_points:
            path_points.extend(segment_points)
        else:
            path_points.extend(segment_points[1:])

        cumulative_distance += segment.length

    return path_points


def sample_segment_at_distance(
    segment: PathSegment,
    local_distance: float,
    global_distance: float,
) -> PathPoint:
    """Sample a single point at specified distance within segment."""
    if segment.length == 0:
        t = 0.0
    else:
        t = local_distance / segment.length

    t = max(0.0, min(1.0, t))

    if segment.segment_type == "line":
        return eval_line_at_t(segment, t, global_distance)
    if segment.segment_type == "cubic":
        return eval_cubic_at_t(segment, t, global_distance)
    if segment.segment_type == "quadratic":
        return eval_quadratic_at_t(segment, t, global_distance)
    return eval_line_at_t(segment, t, global_distance)


def eval_line_at_t(segment: PathSegment, t: float, distance: float) -> PathPoint:
    """Evaluate line segment at parameter t."""
    start, end = segment.start_point, segment.end_point
    x = start.x + t * (end.x - start.x)
    y = start.y + t * (end.y - start.y)

    dx = end.x - start.x
    dy = end.y - start.y
    angle = math.atan2(dy, dx) if (dx != 0 or dy != 0) else 0.0

    return PathPoint(x=x, y=y, tangent_angle=angle, distance_along_path=distance)


def eval_cubic_at_t(segment: PathSegment, t: float, distance: float) -> PathPoint:
    """Evaluate cubic Bezier segment at parameter t."""
    p0 = segment.start_point
    p3 = segment.end_point
    p1, p2 = segment.control_points[0], segment.control_points[1]

    x = (
        (1 - t) ** 3 * p0.x
        + 3 * (1 - t) ** 2 * t * p1.x
        + 3 * (1 - t) * t**2 * p2.x
        + t**3 * p3.x
    )
    y = (
        (1 - t) ** 3 * p0.y
        + 3 * (1 - t) ** 2 * t * p1.y
        + 3 * (1 - t) * t**2 * p2.y
        + t**3 * p3.y
    )

    dx_dt = (
        3 * (1 - t) ** 2 * (p1.x - p0.x)
        + 6 * (1 - t) * t * (p2.x - p1.x)
        + 3 * t**2 * (p3.x - p2.x)
    )
    dy_dt = (
        3 * (1 - t) ** 2 * (p1.y - p0.y)
        + 6 * (1 - t) * t * (p2.y - p1.y)
        + 3 * t**2 * (p3.y - p2.y)
    )

    angle = math.atan2(dy_dt, dx_dt) if (dx_dt != 0 or dy_dt != 0) else 0.0

    return PathPoint(x=x, y=y, tangent_angle=angle, distance_along_path=distance)


def eval_quadratic_at_t(segment: PathSegment, t: float, distance: float) -> PathPoint:
    """Evaluate quadratic Bezier segment at parameter t."""
    p0 = segment.start_point
    p2 = segment.end_point
    p1 = segment.control_points[0]

    x = (1 - t) ** 2 * p0.x + 2 * (1 - t) * t * p1.x + t**2 * p2.x
    y = (1 - t) ** 2 * p0.y + 2 * (1 - t) * t * p1.y + t**2 * p2.y

    dx_dt = 2 * (1 - t) * (p1.x - p0.x) + 2 * t * (p2.x - p1.x)
    dy_dt = 2 * (1 - t) * (p1.y - p0.y) + 2 * t * (p2.y - p1.y)

    angle = math.atan2(dy_dt, dx_dt) if (dx_dt != 0 or dy_dt != 0) else 0.0

    return PathPoint(x=x, y=y, tangent_angle=angle, distance_along_path=distance)


def sample_segment(
    segment: PathSegment,
    num_samples: int,
    base_distance: float,
) -> list[PathPoint]:
    """Sample points along a segment."""
    if segment.segment_type == "line":
        return sample_line_segment(segment, num_samples, base_distance)
    if segment.segment_type == "cubic":
        return sample_cubic_segment(segment, num_samples, base_distance)
    if segment.segment_type == "quadratic":
        return sample_quadratic_segment(segment, num_samples, base_distance)
    return sample_line_segment(segment, num_samples, base_distance)


def sample_line_segment(
    segment: PathSegment,
    num_samples: int,
    base_distance: float,
) -> list[PathPoint]:
    """Sample points along a line segment."""
    points = []
    start = segment.start_point
    end = segment.end_point
    angle_rad = math.atan2(end.y - start.y, end.x - start.x)

    for i in range(num_samples):
        t = i / (num_samples - 1) if num_samples > 1 else 0
        x = start.x + t * (end.x - start.x)
        y = start.y + t * (end.y - start.y)
        distance = base_distance + t * segment.length
        points.append(
            PathPoint(
                x=x,
                y=y,
                tangent_angle=angle_rad,
                distance_along_path=distance,
            )
        )

    return points


def sample_cubic_segment(
    segment: PathSegment,
    num_samples: int,
    base_distance: float,
) -> list[PathPoint]:
    """Sample points along a cubic Bezier segment."""
    points = []
    start = segment.start_point
    cp1, cp2 = segment.control_points
    end = segment.end_point

    for i in range(num_samples):
        t = i / (num_samples - 1) if num_samples > 1 else 0

        x = (
            (1 - t) ** 3 * start.x
            + 3 * (1 - t) ** 2 * t * cp1.x
            + 3 * (1 - t) * t**2 * cp2.x
            + t**3 * end.x
        )
        y = (
            (1 - t) ** 3 * start.y
            + 3 * (1 - t) ** 2 * t * cp1.y
            + 3 * (1 - t) * t**2 * cp2.y
            + t**3 * end.y
        )

        dx_dt = (
            -3 * (1 - t) ** 2 * start.x
            + 3 * (1 - t) ** 2 * cp1.x
            - 6 * (1 - t) * t * cp1.x
            + 6 * (1 - t) * t * cp2.x
            - 3 * t**2 * cp2.x
            + 3 * t**2 * end.x
        )
        dy_dt = (
            -3 * (1 - t) ** 2 * start.y
            + 3 * (1 - t) ** 2 * cp1.y
            - 6 * (1 - t) * t * cp1.y
            + 6 * (1 - t) * t * cp2.y
            - 3 * t**2 * cp2.y
            + 3 * t**2 * end.y
        )

        angle_rad = math.atan2(dy_dt, dx_dt) if dx_dt != 0 or dy_dt != 0 else 0
        distance = base_distance + t * segment.length
        points.append(
            PathPoint(
                x=x,
                y=y,
                tangent_angle=angle_rad,
                distance_along_path=distance,
            )
        )

    return points


def sample_quadratic_segment(
    segment: PathSegment,
    num_samples: int,
    base_distance: float,
) -> list[PathPoint]:
    """Sample points along a quadratic Bezier segment."""
    points = []
    start = segment.start_point
    cp = segment.control_points[0]
    end = segment.end_point

    for i in range(num_samples):
        t = i / (num_samples - 1) if num_samples > 1 else 0
        x = (1 - t) ** 2 * start.x + 2 * (1 - t) * t * cp.x + t**2 * end.x
        y = (1 - t) ** 2 * start.y + 2 * (1 - t) * t * cp.y + t**2 * end.y

        dx_dt = 2 * (1 - t) * (cp.x - start.x) + 2 * t * (end.x - cp.x)
        dy_dt = 2 * (1 - t) * (cp.y - start.y) + 2 * t * (end.y - cp.y)

        angle_rad = math.atan2(dy_dt, dx_dt) if dx_dt != 0 or dy_dt != 0 else 0
        distance = base_distance + t * segment.length
        points.append(
            PathPoint(
                x=x,
                y=y,
                tangent_angle=angle_rad,
                distance_along_path=distance,
            )
        )

    return points


__all__ = [
    "eval_cubic_at_t",
    "eval_line_at_t",
    "eval_quadratic_at_t",
    "fallback_horizontal_line",
    "sample_cubic_segment",
    "sample_line_segment",
    "sample_path_deterministic",
    "sample_path_proportional",
    "sample_quadratic_segment",
    "sample_segment",
    "sample_segment_at_distance",
]
