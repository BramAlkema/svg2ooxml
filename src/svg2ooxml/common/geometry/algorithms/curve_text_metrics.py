"""Interpolation and curvature helpers for sampled text paths."""

from __future__ import annotations

import math

from svg2ooxml.ir.text_path import PathPoint


def find_point_at_distance(
    path_points: list[PathPoint],
    target_distance: float,
) -> PathPoint | None:
    """
    Find path point at specific distance using interpolation.

    Args:
        path_points: List of sampled path points
        target_distance: Target distance along path

    Returns:
        PathPoint at target distance, or None if not found
    """
    if not path_points:
        return None

    if target_distance <= path_points[0].distance_along_path:
        return path_points[0]
    if target_distance >= path_points[-1].distance_along_path:
        return path_points[-1]

    for i in range(len(path_points) - 1):
        curr_point = path_points[i]
        next_point = path_points[i + 1]

        if curr_point.distance_along_path <= target_distance <= next_point.distance_along_path:
            distance_range = next_point.distance_along_path - curr_point.distance_along_path
            if distance_range > 0:
                t = (target_distance - curr_point.distance_along_path) / distance_range
                x = curr_point.x + t * (next_point.x - curr_point.x)
                y = curr_point.y + t * (next_point.y - curr_point.y)
                angle = interpolate_angle(curr_point.tangent_angle, next_point.tangent_angle, t)

                return PathPoint(
                    x=x,
                    y=y,
                    tangent_angle=angle,
                    distance_along_path=target_distance,
                )
            return curr_point

    return None


def interpolate_angle(angle1: float, angle2: float, t: float) -> float:
    """Interpolate between two angles handling wraparound."""
    angle1 = angle1 % (2 * math.pi)
    angle2 = angle2 % (2 * math.pi)

    diff = angle2 - angle1
    if diff > math.pi:
        diff -= 2 * math.pi
    elif diff < -math.pi:
        diff += 2 * math.pi

    return angle1 + t * diff


def calculate_path_curvature(path_points: list[PathPoint], point_index: int) -> float:
    """
    Calculate curvature at a specific path point.

    Args:
        path_points: List of path points
        point_index: Index of point to calculate curvature for

    Returns:
        Curvature value (0 = straight, higher = more curved)
    """
    if len(path_points) < 3 or point_index < 1 or point_index >= len(path_points) - 1:
        return 0.0

    p1 = path_points[point_index - 1]
    p2 = path_points[point_index]
    p3 = path_points[point_index + 1]

    v1 = (p2.x - p1.x, p2.y - p1.y)
    v2 = (p3.x - p2.x, p3.y - p2.y)
    cross = v1[0] * v2[1] - v1[1] * v2[0]
    mag1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    mag2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)

    if mag1 * mag2 > 0:
        return abs(cross) / (mag1 * mag2)
    return 0.0


__all__ = [
    "calculate_path_curvature",
    "find_point_at_distance",
    "interpolate_angle",
]
