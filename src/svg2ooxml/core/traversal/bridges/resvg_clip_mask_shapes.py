"""Shape-to-segment conversion for resvg clip/mask definitions."""

from __future__ import annotations

from collections.abc import Iterable

from svg2ooxml.common.geometry.paths import normalize_path_to_segments
from svg2ooxml.common.geometry.segments import (
    line_segments_from_points,
    transform_segments,
)
from svg2ooxml.core.resvg.geometry.matrix import Matrix as ResvgMatrix
from svg2ooxml.core.resvg.geometry.matrix_bridge import (
    IDENTITY_MATRIX_TUPLE,
    MatrixTuple,
)
from svg2ooxml.core.resvg.geometry.matrix_bridge import (
    matrix_to_tuple as _matrix_to_tuple,
)
from svg2ooxml.core.resvg.geometry.matrix_bridge import (
    transform_point as _matrix_transform_point,
)
from svg2ooxml.core.resvg.usvg_tree import (
    BaseNode,
    CircleNode,
    EllipseNode,
    LineNode,
    PolyNode,
    RectNode,
)
from svg2ooxml.core.traversal.bridges.resvg_clip_mask_bounds import parse_number
from svg2ooxml.core.traversal.constants import DEFAULT_TOLERANCE
from svg2ooxml.ir.geometry import LineSegment, Point, SegmentType


def shape_segments(node: BaseNode, transform: ResvgMatrix) -> list[SegmentType]:
    tag = getattr(node, "tag", "").lower()
    if isinstance(node, RectNode):
        return _rect_segments(
            node.x, node.y, node.width, node.height, node.rx, node.ry, transform
        )
    if isinstance(node, CircleNode):
        return _arc_shape_segments(node.cx, node.cy, node.r, node.r, transform)
    if isinstance(node, EllipseNode):
        return _arc_shape_segments(node.cx, node.cy, node.rx, node.ry, transform)
    if isinstance(node, PolyNode):
        return _poly_segments(node.points, tag == "polygon", transform)
    if isinstance(node, LineNode):
        return _apply_transform_to_segments(
            [LineSegment(Point(node.x1, node.y1), Point(node.x2, node.y2))],
            transform,
        )

    attributes = getattr(node, "attributes", {})
    if tag == "rect":
        return _rect_segments(
            parse_number(attributes.get("x"), 0.0),
            parse_number(attributes.get("y"), 0.0),
            parse_number(attributes.get("width"), 0.0),
            parse_number(attributes.get("height"), 0.0),
            parse_number(attributes.get("rx"), 0.0),
            parse_number(attributes.get("ry"), 0.0),
            transform,
        )
    if tag == "circle":
        return _arc_shape_segments(
            parse_number(attributes.get("cx"), 0.0),
            parse_number(attributes.get("cy"), 0.0),
            parse_number(attributes.get("r"), 0.0),
            parse_number(attributes.get("r"), 0.0),
            transform,
        )

    return []


def _rect_segments(
    x: float,
    y: float,
    width: float,
    height: float,
    rx: float,
    ry: float,
    transform: ResvgMatrix,
) -> list[SegmentType]:
    if rx or ry:
        return []
    return _transform_points(
        [
            Point(x, y),
            Point(x + width, y),
            Point(x + width, y + height),
            Point(x, y + height),
            Point(x, y),
        ],
        transform,
    )


def _arc_shape_segments(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    transform: ResvgMatrix,
) -> list[SegmentType]:
    segments = normalize_path_to_segments(
        f"M {cx - rx} {cy} A {rx} {ry} 0 1 0 {cx + rx} {cy} "
        f"A {rx} {ry} 0 1 0 {cx - rx} {cy}",
        tolerance=DEFAULT_TOLERANCE,
    ).segments
    return _apply_transform_to_segments(segments, transform)


def _poly_segments(
    points_list: tuple[float, ...],
    close_path: bool,
    transform: ResvgMatrix,
) -> list[SegmentType]:
    if not points_list:
        return []
    path_parts = [f"M {points_list[0]} {points_list[1]}"]
    path_parts.extend(
        f"L {points_list[index]} {points_list[index + 1]}"
        for index in range(2, len(points_list), 2)
    )
    segments = normalize_path_to_segments(
        " ".join(path_parts),
        close_path=close_path,
        tolerance=DEFAULT_TOLERANCE,
    ).segments
    return _apply_transform_to_segments(segments, transform)


def _apply_transform_to_segments(
    segments: Iterable[SegmentType],
    transform: ResvgMatrix,
) -> list[SegmentType]:
    tuple_transform = _matrix_to_tuple(transform)
    if tuple_transform == IDENTITY_MATRIX_TUPLE:
        return list(segments)
    return transform_segments(
        segments, lambda point: _transform_point(point, tuple_transform)
    )


def _transform_points(
    points: Iterable[Point], transform: ResvgMatrix
) -> list[SegmentType]:
    tuple_transform = _matrix_to_tuple(transform)
    transformed_points = (_transform_point(point, tuple_transform) for point in points)
    return list(line_segments_from_points(transformed_points))


def _transform_point(point: Point, transform: MatrixTuple) -> Point:
    return _matrix_transform_point(point, transform)
