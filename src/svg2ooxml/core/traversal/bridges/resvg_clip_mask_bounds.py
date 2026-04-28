"""Bounds and metadata helpers for resvg clip/mask conversion."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from svg2ooxml.common.units.lengths import parse_number_or_percent
from svg2ooxml.core.resvg.geometry.matrix_bridge import (
    IDENTITY_MATRIX_TUPLE,
    MatrixTuple,
)
from svg2ooxml.core.resvg.geometry.matrix_bridge import (
    matrix_to_matrix2d as _matrix_to_matrix2d,
)
from svg2ooxml.core.resvg.geometry.matrix_bridge import (
    matrix_to_tuple as _matrix_to_tuple,
)
from svg2ooxml.core.traversal.geometry_utils import transform_axis_aligned_rect
from svg2ooxml.ir.geometry import Point, Rect


def parse_number(value: Any, default: float = 0.0) -> float:
    return parse_number_or_percent(value, default)


def parse_region(attributes: dict[str, Any]) -> Rect | None:
    return Rect(
        x=parse_number(attributes.get("x"), 0.0),
        y=parse_number(attributes.get("y"), 0.0),
        width=parse_number(attributes.get("width"), 0.0),
        height=parse_number(attributes.get("height"), 0.0),
    )


def compute_primitives_bbox(primitives: Iterable[dict[str, Any]]) -> Rect | None:
    points: list[Point] = []
    for primitive in primitives:
        primitive_type = primitive.get("type")
        if primitive_type not in {"rect", "image"}:
            continue
        bounds = primitive_axis_aligned_bounds(primitive)
        if bounds is None:
            continue
        points.extend(
            (
                Point(bounds.x, bounds.y),
                Point(bounds.x + bounds.width, bounds.y),
                Point(bounds.x + bounds.width, bounds.y + bounds.height),
                Point(bounds.x, bounds.y + bounds.height),
            )
        )
    return points_bbox(points)


def primitive_axis_aligned_bounds(primitive: dict[str, Any]) -> Rect | None:
    attributes = primitive.get("attributes", {})
    return transform_axis_aligned_rect(
        _matrix_to_matrix2d(normalize_transform_tuple(primitive.get("transform"))),
        parse_number(attributes.get("x"), 0.0),
        parse_number(attributes.get("y"), 0.0),
        parse_number(attributes.get("width"), 0.0),
        parse_number(attributes.get("height"), 0.0),
    )


def points_bbox(points: Iterable[Point]) -> Rect | None:
    points_list = list(points)
    if not points_list:
        return None
    min_x = min(point.x for point in points_list)
    max_x = max(point.x for point in points_list)
    min_y = min(point.y for point in points_list)
    max_y = max(point.y for point in points_list)
    return Rect(
        x=min_x,
        y=min_y,
        width=max_x - min_x,
        height=max_y - min_y,
    )


def normalize_transform_tuple(value: Any) -> MatrixTuple:
    try:
        return _matrix_to_tuple(value)
    except (TypeError, ValueError):
        return IDENTITY_MATRIX_TUPLE


def normalize_mask_mode(mask_type: str | None) -> str | None:
    if mask_type is None:
        return None
    lowered = mask_type.lower()
    if lowered in {"alpha", "luminance"}:
        return lowered
    return mask_type
