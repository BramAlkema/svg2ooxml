"""Point and vector math shared by geometry algorithms."""

from __future__ import annotations

import math
from typing import Protocol

Vector2 = tuple[float, float]


class PointLike(Protocol):
    x: float
    y: float


def point_distance(a: PointLike, b: PointLike) -> float:
    """Return Euclidean distance between two point-like objects."""

    return math.hypot(a.x - b.x, a.y - b.y)


def point_to_line_distance(point: PointLike, start: PointLike, end: PointLike) -> float:
    """Return perpendicular distance from *point* to the line through *start/end*."""

    dx = end.x - start.x
    dy = end.y - start.y
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-18:
        return point_distance(point, start)
    numerator = abs(dy * point.x - dx * point.y + end.x * start.y - end.y * start.x)
    return numerator / math.sqrt(length_sq)


def vector_between(a: PointLike, b: PointLike) -> Vector2:
    """Return vector ``a - b``."""

    return (a.x - b.x, a.y - b.y)


def dot_vectors(a: Vector2, b: Vector2) -> float:
    return a[0] * b[0] + a[1] * b[1]


def normalize_vector(
    vector: Vector2,
    *,
    fallback: Vector2 = (1.0, 0.0),
    epsilon: float = 1e-12,
) -> Vector2:
    length = math.hypot(vector[0], vector[1])
    if length < epsilon:
        return fallback
    return (vector[0] / length, vector[1] / length)


def points_collinear_by_angle(
    start: PointLike,
    mid: PointLike,
    end: PointLike,
    angle_rad: float,
    *,
    epsilon: float = 1e-9,
) -> bool:
    """Return true when directions ``start->mid`` and ``start->end`` nearly match."""

    v1 = (mid.x - start.x, mid.y - start.y)
    v2 = (end.x - start.x, end.y - start.y)
    len1 = math.hypot(v1[0], v1[1])
    len2 = math.hypot(v2[0], v2[1])
    if len1 < epsilon or len2 < epsilon:
        return True
    cos_angle = dot_vectors(v1, v2) / (len1 * len2)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    return math.acos(cos_angle) < angle_rad


__all__ = [
    "Vector2",
    "PointLike",
    "dot_vectors",
    "normalize_vector",
    "point_distance",
    "point_to_line_distance",
    "points_collinear_by_angle",
    "vector_between",
]
