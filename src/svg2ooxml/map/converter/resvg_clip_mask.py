"""Convert resvg clipPath and mask nodes into legacy clip/mask definitions."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from svg2ooxml.clipmask.types import ClipDefinition, MaskInfo
from svg2ooxml.core.resvg.geometry.matrix import Matrix as ResvgMatrix
from svg2ooxml.core.resvg.usvg_tree import BaseNode, Tree
from svg2ooxml.geometry.paths import compute_segments_bbox
from svg2ooxml.geometry.paths.resvg_bridge import normalize_path_to_segments
from svg2ooxml.ir.geometry import LineSegment, Point, Rect, SegmentType
from svg2ooxml.map.converter.constants import DEFAULT_TOLERANCE
from svg2ooxml.parser.geometry.matrix import Matrix2D


def collect_resvg_clip_definitions(tree: Tree | None) -> dict[str, ClipDefinition]:
    """Return clip definitions composed from resvg clipPath nodes."""

    if tree is None or not getattr(tree, "clip_paths", None):
        return {}

    definitions: dict[str, ClipDefinition] = {}
    for clip_id, clip_node in tree.clip_paths.items():
        segments: list[SegmentType] = []
        primitives: list[dict[str, Any]] = []
        _gather_segments(
            clip_node.children,
            clip_node.transform,
            tree,
            segments_out=segments,
            primitives_out=primitives,
            visited=set(),
        )
        if not segments:
            continue
        bbox = compute_segments_bbox(segments)
        clip_rule = (
            clip_node.attributes.get("clip-rule")
            or clip_node.styles.get("clip-rule")
            or None
        )
        definitions[clip_id] = ClipDefinition(
            clip_id=clip_id,
            segments=tuple(segments),
            bounding_box=bbox,
            clip_rule=clip_rule,
            transform=_matrix_to_matrix2d(clip_node.transform),
            primitives=tuple(primitives),
        )
    return definitions


def collect_resvg_mask_info(tree: Tree | None) -> dict[str, MaskInfo]:
    """Return mask info derived from resvg mask nodes."""

    if tree is None or not getattr(tree, "masks", None):
        return {}

    masks: dict[str, MaskInfo] = {}
    for mask_id, mask_node in tree.masks.items():
        segments: list[SegmentType] = []
        primitives: list[dict[str, Any]] = []
        hints: dict[str, Any] = {"has_raster": False, "unsupported_nodes": []}
        _gather_segments(
            mask_node.children,
            mask_node.transform,
            tree,
            segments_out=segments,
            primitives_out=primitives,
            visited=set(),
            hints=hints,
        )
        bbox = compute_segments_bbox(segments) if segments else None
        mask_type = mask_node.attributes.get("mask-type") or mask_node.attributes.get("maskType")
        mode = _normalize_mask_mode(mask_type)
        opacity = getattr(mask_node.presentation, "opacity", None)
        region = _parse_region(mask_node.attributes)
        raw_region = {
            key: mask_node.attributes.get(key)
            for key in ("x", "y", "width", "height")
        }
        policy_hints: dict[str, Any] = {}
        if hints.get("has_raster"):
            policy_hints.setdefault("mask", {})["requires_raster"] = True
        if hints.get("unsupported_nodes"):
            policy_hints.setdefault("mask", {})["unsupported_nodes"] = tuple(hints["unsupported_nodes"])

        masks[mask_id] = MaskInfo(
            mask_id=mask_id,
            mask_type=mask_type,
            mode=mode,
            mask_units=mask_node.mask_units,
            mask_content_units=mask_node.mask_content_units,
            region=region,
            opacity=opacity,
            transform=_matrix_to_matrix2d(mask_node.transform),
            children=tuple(
                getattr(child, "id", None) for child in mask_node.children if getattr(child, "id", None)
            ),
            bounding_box=bbox,
            segments=tuple(segments),
            content_xml=tuple(
                _serialize_source(child)
                for child in mask_node.children
                if _serialize_source(child) is not None
            ),
            primitives=tuple(primitives),
            raw_region={k: v for k, v in raw_region.items() if v is not None},
            policy_hints=policy_hints,
        )
    return masks


def _gather_segments(
    nodes: Iterable[BaseNode],
    parent_transform: ResvgMatrix | None,
    tree: Tree,
    *,
    segments_out: List[SegmentType],
    primitives_out: List[dict[str, Any]],
    visited: set[str],
    hints: dict[str, Any] | None = None,
) -> None:
    combined_parent = parent_transform or ResvgMatrix.identity()
    for node in nodes:
        node_transform = _combine_transform(combined_parent, getattr(node, "transform", None))
        tag = getattr(node, "tag", "").lower()

        if tag == "use":
            href = getattr(node, "href", None) or getattr(node, "attributes", {}).get("href")
            if href and href.startswith("#"):
                ref_id = href[1:]
                if ref_id in visited:
                    continue
                referenced = getattr(tree, "ids", {}).get(ref_id)
                if referenced is None:
                    continue
                visited.add(ref_id)
                referenced_children = referenced.children if referenced.children else [referenced]
                _gather_segments(
                    referenced_children,
                    node_transform,
                    tree,
                    segments_out=segments_out,
                    primitives_out=primitives_out,
                    visited=visited,
                    hints=hints,
                )
                visited.discard(ref_id)
            continue

        if tag == "path":
            path_data = getattr(node, "d", None)
            if not path_data:
                continue
            try:
                normalized = normalize_path_to_segments(
                    path_data,
                    transform=_matrix_to_tuple(node_transform),
                    tolerance=DEFAULT_TOLERANCE,
                )
            except Exception:
                continue
            segments_out.extend(normalized.segments)
            primitives_out.append(
                {
                    "type": "path",
                    "d": path_data,
                    "transform": _matrix_to_tuple(node_transform),
                }
            )
            continue

        if tag in {"g", "svg", "clippath", "mask"}:
            _gather_segments(
                node.children,
                node_transform,
                tree,
                segments_out=segments_out,
                primitives_out=primitives_out,
                visited=visited,
                hints=hints,
            )
            continue

        if tag in {"rect", "circle", "ellipse", "polygon", "polyline", "line"}:
            shape_segments = _shape_segments(node, node_transform)
            segments_out.extend(shape_segments)
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
            elif tag == "circle":
                primitive_info.update(
                    {
                        "cx": attributes.get("cx"),
                        "cy": attributes.get("cy"),
                        "r": attributes.get("r"),
                    }
                )
            elif tag == "ellipse":
                primitive_info.update(
                    {
                        "cx": attributes.get("cx"),
                        "cy": attributes.get("cy"),
                        "rx": attributes.get("rx"),
                        "ry": attributes.get("ry"),
                    }
                )
            elif tag == "line":
                primitive_info.update(
                    {
                        "x1": attributes.get("x1"),
                        "y1": attributes.get("y1"),
                        "x2": attributes.get("x2"),
                        "y2": attributes.get("y2"),
                    }
                )
            elif tag in {"polygon", "polyline"}:
                primitive_info["points"] = attributes.get("points")
            primitives_out.append(primitive_info)
            continue

        if tag == "image":
            primitives_out.append(
                {
                    "type": "image",
                    "attributes": dict(getattr(node, "attributes", {})),
                    "transform": _matrix_to_tuple(node_transform),
                }
            )
            if hints is not None:
                hints["has_raster"] = True
            continue

        serialized = _serialize_source(node)
        if serialized is not None:
            primitives_out.append(
                {
                    "type": tag or "unknown",
                    "serialized": serialized,
                    "transform": _matrix_to_tuple(node_transform),
                }
            )
        if hints is not None:
            hints.setdefault("unsupported_nodes", []).append(tag)


def _shape_segments(node: BaseNode, transform: ResvgMatrix) -> List[SegmentType]:
    tag = getattr(node, "tag", "").lower()
    if tag == "rect":
        x = float(node.attributes.get("x", node.attributes.get("x", 0.0)) or 0.0)
        y = float(node.attributes.get("y", node.attributes.get("y", 0.0)) or 0.0)
        width = float(node.attributes.get("width") or 0.0)
        height = float(node.attributes.get("height") or 0.0)
        if width == 0.0 or height == 0.0:
            return []
        points = [
            Point(x, y),
            Point(x + width, y),
            Point(x + width, y + height),
            Point(x, y + height),
        ]
        return _build_segments(points, transform, closed=True)
    if tag == "circle":
        cx = float(node.attributes.get("cx") or 0.0)
        cy = float(node.attributes.get("cy") or 0.0)
        r = float(node.attributes.get("r") or 0.0)
        if r <= 0.0:
            return []
        return _circle_segments(cx, cy, r, r, transform)
    if tag == "ellipse":
        cx = float(node.attributes.get("cx") or 0.0)
        cy = float(node.attributes.get("cy") or 0.0)
        rx = float(node.attributes.get("rx") or 0.0)
        ry = float(node.attributes.get("ry") or 0.0)
        if rx <= 0.0 or ry <= 0.0:
            return []
        return _circle_segments(cx, cy, rx, ry, transform)
    if tag in {"polygon", "polyline"}:
        raw_points = getattr(node, "points", ())
        points = [
            Point(raw_points[i], raw_points[i + 1])
            for i in range(0, len(raw_points) - 1, 2)
        ]
        if not points:
            return []
        closed = tag == "polygon"
        return _build_segments(points, transform, closed=closed)
    if tag == "line":
        x1 = float(node.attributes.get("x1") or 0.0)
        y1 = float(node.attributes.get("y1") or 0.0)
        x2 = float(node.attributes.get("x2") or 0.0)
        y2 = float(node.attributes.get("y2") or 0.0)
        start = _apply_matrix(transform, Point(x1, y1))
        end = _apply_matrix(transform, Point(x2, y2))
        if start == end:
            return []
        return [LineSegment(start=start, end=end)]
    return []


def _build_segments(points: List[Point], transform: ResvgMatrix, *, closed: bool) -> List[SegmentType]:
    if not points:
        return []
    transformed = [_apply_matrix(transform, pt) for pt in points]
    segments: list[SegmentType] = []
    for idx in range(len(transformed) - 1):
        segments.append(LineSegment(start=transformed[idx], end=transformed[idx + 1]))
    if closed and transformed[0] != transformed[-1]:
        segments.append(LineSegment(start=transformed[-1], end=transformed[0]))
    return segments


def _circle_segments(cx: float, cy: float, rx: float, ry: float, transform: ResvgMatrix) -> List[SegmentType]:
    points = [
        Point(cx - rx, cy - ry),
        Point(cx + rx, cy - ry),
        Point(cx + rx, cy + ry),
        Point(cx - rx, cy + ry),
    ]
    return _build_segments(points, transform, closed=True)


def _matrix_to_tuple(matrix: ResvgMatrix | None) -> Tuple[float, float, float, float, float, float]:
    if matrix is None:
        matrix = ResvgMatrix.identity()
    return (matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f)


def _matrix_to_matrix2d(matrix: ResvgMatrix | None) -> Matrix2D | None:
    if matrix is None:
        return None
    return Matrix2D(a=matrix.a, b=matrix.b, c=matrix.c, d=matrix.d, e=matrix.e, f=matrix.f)


def _combine_transform(parent: ResvgMatrix, child: ResvgMatrix | None) -> ResvgMatrix:
    if child is None:
        return parent
    return parent.multiply(child)


def _apply_matrix(matrix: ResvgMatrix, point: Point) -> Point:
    x, y = matrix.apply_to_point(point.x, point.y)
    return Point(x, y)


def _serialize_source(node: BaseNode) -> str | None:
    source = getattr(node, "source", None)
    if source is None:
        return None
    try:
        from lxml import etree

        return etree.tostring(source, encoding="unicode")
    except Exception:
        return None


def _parse_region(attrs: Dict[str, str]) -> Rect | None:
    try:
        x = float(attrs.get("x", 0.0) or 0.0)
        y = float(attrs.get("y", 0.0) or 0.0)
        width = float(attrs.get("width", 0.0) or 0.0)
        height = float(attrs.get("height", 0.0) or 0.0)
    except (TypeError, ValueError):
        return None
    if width <= 0.0 or height <= 0.0:
        return None
    return Rect(x, y, width, height)


def _normalize_mask_mode(mask_type: str | None) -> str:
    if mask_type is None:
        return "alpha"
    token = mask_type.strip().lower()
    if token in {"alpha", "luminance"}:
        return token
    return "alpha"


__all__ = ["collect_resvg_clip_definitions", "collect_resvg_mask_info"]
