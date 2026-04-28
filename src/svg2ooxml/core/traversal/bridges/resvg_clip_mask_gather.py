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
