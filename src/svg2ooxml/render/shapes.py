"""Helpers for deriving geometric primitives from SVG nodes."""

from __future__ import annotations

from collections.abc import Iterable

from svg2ooxml.core.resvg.geometry.path_normalizer import NormalizedPath, normalize_path
from svg2ooxml.core.resvg.usvg_tree import (
    BaseNode,
    CircleNode,
    EllipseNode,
    LineNode,
    PathNode,
    PolyNode,
    RectNode,
)


def node_geometry(node: BaseNode) -> NormalizedPath | None:
    if isinstance(node, PathNode):
        return node.geometry
    if isinstance(node, RectNode):
        return _rect_geometry(node)
    if isinstance(node, CircleNode):
        return _circle_geometry(node)
    if isinstance(node, EllipseNode):
        return _ellipse_geometry(node)
    if isinstance(node, LineNode):
        return _line_geometry(node)
    if isinstance(node, PolyNode):
        return _poly_geometry(node)
    return None


def _rect_geometry(node: RectNode) -> NormalizedPath | None:
    width = node.width
    height = node.height
    if width <= 0 or height <= 0:
        return None
    x = node.x
    y = node.y
    x2 = x + width
    y2 = y + height
    path = f"M {_fmt(x)} {_fmt(y)} L {_fmt(x2)} {_fmt(y)} L {_fmt(x2)} {_fmt(y2)} L {_fmt(x)} {_fmt(y2)} Z"
    stroke_width = node.stroke.width if node.stroke else None
    return normalize_path(path, node.transform, stroke_width)


def _circle_geometry(node: CircleNode) -> NormalizedPath | None:
    radius = node.r
    if radius <= 0:
        return None
    cx = node.cx
    cy = node.cy
    r = radius
    d = (
        f"M {_fmt(cx + r)} {_fmt(cy)} "
        f"A {_fmt(r)} {_fmt(r)} 0 1 0 {_fmt(cx - r)} {_fmt(cy)} "
        f"A {_fmt(r)} {_fmt(r)} 0 1 0 {_fmt(cx + r)} {_fmt(cy)} Z"
    )
    stroke_width = node.stroke.width if node.stroke else None
    return normalize_path(d, node.transform, stroke_width)


def _ellipse_geometry(node: EllipseNode) -> NormalizedPath | None:
    rx = node.rx
    ry = node.ry
    if rx <= 0 or ry <= 0:
        return None
    cx = node.cx
    cy = node.cy
    d = (
        f"M {_fmt(cx + rx)} {_fmt(cy)} "
        f"A {_fmt(rx)} {_fmt(ry)} 0 1 0 {_fmt(cx - rx)} {_fmt(cy)} "
        f"A {_fmt(rx)} {_fmt(ry)} 0 1 0 {_fmt(cx + rx)} {_fmt(cy)} Z"
    )
    stroke_width = node.stroke.width if node.stroke else None
    return normalize_path(d, node.transform, stroke_width)


def _line_geometry(node: LineNode) -> NormalizedPath | None:
    x1, y1, x2, y2 = node.x1, node.y1, node.x2, node.y2
    if x1 == x2 and y1 == y2:
        return None
    d = f"M {_fmt(x1)} {_fmt(y1)} L {_fmt(x2)} {_fmt(y2)}"
    stroke_width = node.stroke.width if node.stroke else None
    return normalize_path(d, node.transform, stroke_width)


def _poly_geometry(node: PolyNode) -> NormalizedPath | None:
    points = node.points
    if len(points) < 4:
        return None
    coords = list(_iter_pairs(points))
    d_parts = [f"M {_fmt(coords[0][0])} {_fmt(coords[0][1])}"]
    for x, y in coords[1:]:
        d_parts.append(f"L {_fmt(x)} {_fmt(y)}")
    if node.tag == "polygon" and coords[0] != coords[-1]:
        d_parts.append("Z")
    path_data = " ".join(d_parts)
    stroke_width = node.stroke.width if node.stroke else None
    return normalize_path(path_data, node.transform, stroke_width)


def _iter_pairs(values: Iterable[float]) -> Iterable[tuple[float, float]]:
    iterator = iter(values)
    for x in iterator:
        y = next(iterator, None)
        if y is None:
            break
        yield x, y


def _fmt(value: float) -> str:
    formatted = f"{value:.6f}"
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted


__all__ = ["node_geometry"]
