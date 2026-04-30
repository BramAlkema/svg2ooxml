"""Recursive geometry gathering for resvg clip/mask definitions."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from svg2ooxml.common.geometry.paths import normalize_path_to_segments
from svg2ooxml.common.svg_refs import local_url_id
from svg2ooxml.core.resvg.geometry.matrix import Matrix as ResvgMatrix
from svg2ooxml.core.resvg.geometry.matrix_bridge import (
    matrix_to_tuple as _matrix_to_tuple,
)
from svg2ooxml.core.resvg.usvg_tree import BaseNode, Tree
from svg2ooxml.core.traversal.bridges.resvg_clip_mask_shapes import shape_segments
from svg2ooxml.core.traversal.constants import DEFAULT_TOLERANCE
from svg2ooxml.drawingml.skia_path import skia, skia_path_from_segments
from svg2ooxml.ir.geometry import SegmentType

_CONTAINER_TAGS = {"g", "svg", "clippath", "mask"}
_SHAPE_TAGS = {"rect", "circle", "ellipse", "polygon", "polyline", "line"}


def gather_segments(
    nodes: Iterable[BaseNode],
    parent_transform: ResvgMatrix | None,
    tree: Tree,
    *,
    segments_out: list[SegmentType],
    primitives_out: list[dict[str, Any]],
    visited: set[str],
    hints: dict[str, Any] | None = None,
) -> None:
    combined_parent = parent_transform or ResvgMatrix.identity()
    for node in nodes:
        if _is_non_rendered(node):
            continue
        node_transform = _combine_transform(
            combined_parent, getattr(node, "transform", None)
        )
        tag = getattr(node, "tag", "").lower()

        if tag == "use":
            _gather_use_node(
                node,
                node_transform,
                tree,
                segments_out=segments_out,
                primitives_out=primitives_out,
                visited=visited,
                hints=hints,
            )
            continue

        if tag == "path":
            _append_path_node(node, node_transform, segments_out, primitives_out)
            continue

        if tag in _CONTAINER_TAGS:
            gather_segments(
                node.children,
                node_transform,
                tree,
                segments_out=segments_out,
                primitives_out=primitives_out,
                visited=visited,
                hints=hints,
            )
            continue

        if tag in _SHAPE_TAGS:
            _append_shape_node(node, node_transform, segments_out, primitives_out, tag)
            continue

        if tag == "image":
            _append_image_node(node, node_transform, primitives_out, hints)
            continue

        if hints is not None:
            hints["unsupported_nodes"].append(tag or "unknown")


def gather_clip_path(
    node: BaseNode,
    parent_transform: ResvgMatrix | None,
    tree: Tree,
    *,
    visited: set[str],
):
    """Return a Skia path for a clipPath, applying SVG clip intersections."""

    if skia is None:
        return None
    combined_parent = parent_transform or ResvgMatrix.identity()
    base = _union_paths(
        _node_path(child, combined_parent, tree, visited)
        for child in getattr(node, "children", ()) or ()
    )
    if base is None or base.isEmpty():
        return None
    return _apply_node_clip(base, node, tree, visited)


def _gather_use_node(
    node: BaseNode,
    node_transform: ResvgMatrix,
    tree: Tree,
    *,
    segments_out: list[SegmentType],
    primitives_out: list[dict[str, Any]],
    visited: set[str],
    hints: dict[str, Any] | None,
) -> None:
    href = getattr(node, "href", None) or getattr(node, "attributes", {}).get("href")
    ref_id = local_url_id(href)
    if ref_id is None or ref_id in visited:
        return
    referenced = getattr(tree, "ids", {}).get(ref_id)
    if referenced is None:
        return

    visited.add(ref_id)
    referenced_children = referenced.children if referenced.children else [referenced]
    gather_segments(
        referenced_children,
        node_transform,
        tree,
        segments_out=segments_out,
        primitives_out=primitives_out,
        visited=visited,
        hints=hints,
    )
    visited.discard(ref_id)


def _node_path(
    node: BaseNode,
    parent_transform: ResvgMatrix,
    tree: Tree,
    visited: set[str],
):
    if _is_non_rendered(node):
        return None
    node_transform = _combine_transform(parent_transform, getattr(node, "transform", None))
    tag = getattr(node, "tag", "").lower()
    result = None

    if tag == "use":
        result = _use_node_path(node, node_transform, tree, visited)
    elif tag == "path":
        result = _path_node_path(node, node_transform)
    elif tag in _CONTAINER_TAGS:
        result = _union_paths(
            _node_path(child, node_transform, tree, visited)
            for child in getattr(node, "children", ()) or ()
        )
    elif tag in _SHAPE_TAGS:
        result = _shape_node_path(node, node_transform, tag)
    elif tag == "image":
        result = _image_node_path(node, node_transform)

    if result is None or result.isEmpty():
        return None
    return _apply_node_clip(result, node, tree, visited)


def _use_node_path(
    node: BaseNode,
    node_transform: ResvgMatrix,
    tree: Tree,
    visited: set[str],
):
    href = getattr(node, "href", None) or getattr(node, "attributes", {}).get("href")
    ref_id = local_url_id(href)
    if ref_id is None or ref_id in visited:
        return None
    referenced = getattr(tree, "ids", {}).get(ref_id)
    if referenced is None:
        return None

    visited.add(ref_id)
    try:
        referenced_children = referenced.children if referenced.children else [referenced]
        return _union_paths(
            _node_path(child, node_transform, tree, visited)
            for child in referenced_children
        )
    finally:
        visited.discard(ref_id)


def _path_node_path(node: BaseNode, node_transform: ResvgMatrix):
    path_data = getattr(node, "d", None)
    if not path_data:
        return None
    try:
        normalized = normalize_path_to_segments(
            path_data,
            transform=_matrix_to_tuple(node_transform),
            tolerance=DEFAULT_TOLERANCE,
        )
    except Exception:
        return None
    rule = _clip_rule(node)
    return skia_path_from_segments(normalized.segments, closed=True, fill_rule=rule)


def _shape_node_path(node: BaseNode, node_transform: ResvgMatrix, tag: str):
    if skia is None:
        return None
    path = skia.Path()
    try:
        if tag == "rect":
            path.addRect(
                skia.Rect.MakeXYWH(
                    float(getattr(node, "x", 0.0)),
                    float(getattr(node, "y", 0.0)),
                    float(getattr(node, "width", 0.0)),
                    float(getattr(node, "height", 0.0)),
                )
            )
        elif tag == "circle":
            path.addCircle(
                float(getattr(node, "cx", 0.0)),
                float(getattr(node, "cy", 0.0)),
                float(getattr(node, "r", 0.0)),
            )
        elif tag == "ellipse":
            cx = float(getattr(node, "cx", 0.0))
            cy = float(getattr(node, "cy", 0.0))
            rx = float(getattr(node, "rx", 0.0))
            ry = float(getattr(node, "ry", 0.0))
            path.addOval(skia.Rect.MakeLTRB(cx - rx, cy - ry, cx + rx, cy + ry))
        else:
            segments = shape_segments(node, node_transform)
            return skia_path_from_segments(segments, closed=True, fill_rule=_clip_rule(node))
    except Exception:
        return None
    _apply_transform_in_place(path, node_transform)
    if _is_even_odd(_clip_rule(node)):
        path.setFillType(skia.PathFillType.kEvenOdd)
    return None if path.isEmpty() else path


def _image_node_path(node: BaseNode, node_transform: ResvgMatrix):
    if skia is None:
        return None
    width = getattr(node, "width", None)
    height = getattr(node, "height", None)
    if width is None or height is None:
        return None
    path = skia.Path()
    path.addRect(
        skia.Rect.MakeXYWH(
            float(getattr(node, "x", 0.0)),
            float(getattr(node, "y", 0.0)),
            float(width),
            float(height),
        )
    )
    _apply_transform_in_place(path, node_transform)
    return None if path.isEmpty() else path


def _apply_node_clip(path, node: BaseNode, tree: Tree, visited: set[str]):
    clip_href = getattr(node, "attributes", {}).get("clip-path") or getattr(
        node, "styles", {}
    ).get("clip-path")
    if not clip_href:
        use_source = getattr(node, "use_source", None)
        get_attr = getattr(use_source, "get", None)
        if callable(get_attr):
            clip_href = get_attr("clip-path")
    clip_id = local_url_id(clip_href)
    if clip_id is None or clip_id in visited:
        return path
    clip_node = getattr(tree, "clip_paths", {}).get(clip_id)
    if clip_node is None:
        return path
    visited.add(clip_id)
    try:
        clip_path = gather_clip_path(
            clip_node,
            getattr(clip_node, "transform", None),
            tree,
            visited=visited,
        )
    finally:
        visited.discard(clip_id)
    if clip_path is None or clip_path.isEmpty():
        return path
    try:
        return skia.Op(path, clip_path, skia.PathOp.kIntersect_PathOp)
    except Exception:
        return path


def _union_paths(paths):
    if skia is None:
        return None
    result = None
    for candidate in paths:
        if candidate is None or candidate.isEmpty():
            continue
        if result is None:
            result = skia.Path(candidate)
            continue
        try:
            result = skia.Op(result, candidate, skia.PathOp.kUnion_PathOp)
        except Exception:
            result.addPath(candidate)
    return result


def _apply_transform_in_place(path, matrix: ResvgMatrix) -> None:
    if skia is None:
        return
    if matrix == ResvgMatrix.identity():
        return
    skia_matrix = skia.Matrix()
    skia_matrix.setAffine(
        [
            float(matrix.a),
            float(matrix.b),
            float(matrix.c),
            float(matrix.d),
            float(matrix.e),
            float(matrix.f),
        ]
    )
    path.transform(skia_matrix)


def _clip_rule(node: BaseNode) -> str | None:
    attrs = getattr(node, "attributes", {}) or {}
    styles = getattr(node, "styles", {}) or {}
    return (
        attrs.get("clip-rule")
        or styles.get("clip-rule")
        or attrs.get("fill-rule")
        or styles.get("fill-rule")
    )


def _is_even_odd(rule: str | None) -> bool:
    return isinstance(rule, str) and rule.strip().lower() in {"evenodd", "even-odd"}


def _append_path_node(
    node: BaseNode,
    node_transform: ResvgMatrix,
    segments_out: list[SegmentType],
    primitives_out: list[dict[str, Any]],
) -> None:
    path_data = getattr(node, "d", None)
    if not path_data:
        return
    try:
        normalized = normalize_path_to_segments(
            path_data,
            transform=_matrix_to_tuple(node_transform),
            tolerance=DEFAULT_TOLERANCE,
        )
    except Exception:
        return
    segments_out.extend(normalized.segments)
    primitives_out.append(
        {
            "type": "path",
            "d": path_data,
            "transform": _matrix_to_tuple(node_transform),
        }
    )


def _append_shape_node(
    node: BaseNode,
    node_transform: ResvgMatrix,
    segments_out: list[SegmentType],
    primitives_out: list[dict[str, Any]],
    tag: str,
) -> None:
    segments_out.extend(shape_segments(node, node_transform))
    attributes = dict(getattr(node, "attributes", {}))
    primitive_info: dict[str, Any] = {
        "type": tag,
        "attributes": attributes,
        "transform": _matrix_to_tuple(node_transform),
    }
    if tag == "rect":
        primitive_info.update(
            {
                "x": attributes.get("x"),
                "y": attributes.get("y"),
                "width": attributes.get("width"),
                "height": attributes.get("height"),
                "rx": attributes.get("rx"),
                "ry": attributes.get("ry"),
            }
        )
    primitives_out.append(primitive_info)


def _append_image_node(
    node: BaseNode,
    node_transform: ResvgMatrix,
    primitives_out: list[dict[str, Any]],
    hints: dict[str, Any] | None,
) -> None:
    if hints is not None:
        hints["has_raster"] = True
    primitives_out.append(
        {
            "type": "image",
            "attributes": dict(getattr(node, "attributes", {})),
            "transform": _matrix_to_tuple(node_transform),
        }
    )


def _combine_transform(
    parent: ResvgMatrix,
    child: ResvgMatrix | None,
) -> ResvgMatrix:
    if child is None:
        return parent
    return parent.multiply(child)


def _is_non_rendered(node: BaseNode) -> bool:
    display = _presentation_value(node, "display")
    if _is_none_value(display):
        return True
    visibility = _presentation_value(node, "visibility")
    if _is_hidden_visibility(visibility):
        return True
    return False


def _presentation_value(node: BaseNode, name: str) -> str | None:
    attrs = getattr(node, "attributes", {}) or {}
    styles = getattr(node, "styles", {}) or {}
    value = attrs.get(name)
    if styles.get(name) is not None:
        value = styles.get(name)
    if value is None:
        use_source = getattr(node, "use_source", None)
        get_attr = getattr(use_source, "get", None)
        if callable(get_attr):
            value = get_attr(name)
    return str(value).strip().lower() if value is not None else None


def _is_none_value(value: str | None) -> bool:
    return value == "none"


def _is_hidden_visibility(value: str | None) -> bool:
    return value in {"hidden", "collapse"}
