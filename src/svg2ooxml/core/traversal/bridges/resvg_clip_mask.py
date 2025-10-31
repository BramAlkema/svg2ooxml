"""Convert resvg clipPath and mask nodes into core clip/mask definitions."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from svg2ooxml.clipmask.types import ClipDefinition, MaskInfo
from svg2ooxml.core.resvg.geometry.matrix import Matrix as ResvgMatrix
from svg2ooxml.core.resvg.usvg_tree import BaseNode, Tree
from svg2ooxml.common.geometry.paths import compute_segments_bbox, normalize_path_to_segments
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect, SegmentType
from svg2ooxml.core.traversal.constants import DEFAULT_TOLERANCE
from svg2ooxml.common.geometry import Matrix2D


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
        if not segments and not primitives:
            continue
        bbox = compute_segments_bbox(segments) if segments else _compute_primitives_bbox(primitives)
        if bbox is None:
            continue
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
        bbox = compute_segments_bbox(segments) if segments else _compute_primitives_bbox(primitives)
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
            primitives_out.append(primitive_info)
            continue

        if tag == "image":
            if hints is not None:
                hints["has_raster"] = True
            primitives_out.append(
                {
                    "type": "image",
                    "attributes": dict(getattr(node, "attributes", {})),
                    "transform": _matrix_to_tuple(node_transform),
                }
            )
            continue

        if hints is not None:
            hints["unsupported_nodes"].append(tag or "unknown")


def _shape_segments(node: BaseNode, transform: ResvgMatrix) -> List[SegmentType]:
    attributes = getattr(node, "attributes", {})
    tag = getattr(node, "tag", "").lower()
    if tag == "rect":
        x = float(attributes.get("x", 0.0) or 0.0)
        y = float(attributes.get("y", 0.0) or 0.0)
        width = float(attributes.get("width", 0.0) or 0.0)
        height = float(attributes.get("height", 0.0) or 0.0)
        rx = attributes.get("rx")
        ry = attributes.get("ry")
        if rx or ry:
            return []
        points = [
            Point(x, y),
            Point(x + width, y),
            Point(x + width, y + height),
            Point(x, y + height),
            Point(x, y),
        ]
        return _transform_points(points, transform)

    if tag == "circle":
        cx = float(attributes.get("cx", 0.0) or 0.0)
        cy = float(attributes.get("cy", 0.0) or 0.0)
        radius = float(attributes.get("r", 0.0) or 0.0)
        segments = normalize_path_to_segments(
            f"M {cx - radius} {cy} A {radius} {radius} 0 1 0 {cx + radius} {cy} "
            f"A {radius} {radius} 0 1 0 {cx - radius} {cy}",
            tolerance=DEFAULT_TOLERANCE,
        ).segments
        return _apply_transform_to_segments(segments, transform)

    if tag == "ellipse":
        cx = float(attributes.get("cx", 0.0) or 0.0)
        cy = float(attributes.get("cy", 0.0) or 0.0)
        rx = float(attributes.get("rx", 0.0) or 0.0)
        ry = float(attributes.get("ry", 0.0) or 0.0)
        segments = normalize_path_to_segments(
            f"M {cx - rx} {cy} A {rx} {ry} 0 1 0 {cx + rx} {cy} "
            f"A {rx} {ry} 0 1 0 {cx - rx} {cy}",
            tolerance=DEFAULT_TOLERANCE,
        ).segments
        return _apply_transform_to_segments(segments, transform)

    if tag in {"polygon", "polyline"}:
        points_attr = attributes.get("points", "")
        segments = normalize_path_to_segments(
            f"M {points_attr}",
            close_path=(tag == "polygon"),
            tolerance=DEFAULT_TOLERANCE,
        ).segments
        return _apply_transform_to_segments(segments, transform)

    if tag == "line":
        x1 = float(attributes.get("x1", 0.0) or 0.0)
        y1 = float(attributes.get("y1", 0.0) or 0.0)
        x2 = float(attributes.get("x2", 0.0) or 0.0)
        y2 = float(attributes.get("y2", 0.0) or 0.0)
        return _apply_transform_to_segments(
            [
                LineSegment(Point(x1, y1), Point(x2, y2)),
            ],
            transform,
        )

    return []


def _apply_transform_to_segments(segments: Iterable[SegmentType], transform: ResvgMatrix) -> List[SegmentType]:
    tuple_transform = _matrix_to_tuple(transform)
    if tuple_transform == (1.0, 0.0, 0.0, 1.0, 0.0, 0.0):
        return list(segments)
    transformed: list[SegmentType] = []
    for segment in segments:
        if isinstance(segment, LineSegment):
            transformed.append(
                LineSegment(
                    start=_transform_point(segment.start, tuple_transform),
                    end=_transform_point(segment.end, tuple_transform),
                )
            )
        elif isinstance(segment, BezierSegment):
            transformed.append(
                BezierSegment(
                    start=_transform_point(segment.start, tuple_transform),
                    control1=_transform_point(segment.control1, tuple_transform),
                    control2=_transform_point(segment.control2, tuple_transform),
                    end=_transform_point(segment.end, tuple_transform),
                )
            )
        else:  # pragma: no cover - defensive fallback for unexpected segment types
            transformed.append(segment)
    return transformed


def _transform_points(points: Iterable[Point], transform: ResvgMatrix) -> List[SegmentType]:
    tuple_transform = _matrix_to_tuple(transform)
    transformed: list[SegmentType] = []
    previous_point: Point | None = None
    for point in points:
        transformed_point = _transform_point(point, tuple_transform)
        if previous_point is not None:
            transformed.append(LineSegment(previous_point, transformed_point))
        previous_point = transformed_point
    return transformed


def _transform_point(point: Point, transform: Tuple[float, float, float, float, float, float]) -> Point:
    a, b, c, d, e, f = transform
    x = a * point.x + c * point.y + e
    y = b * point.x + d * point.y + f
    return Point(x, y)


def _normalize_transform_tuple(value: Any) -> Tuple[float, float, float, float, float, float]:
    if isinstance(value, tuple) and len(value) == 6:
        return tuple(float(component) for component in value)
    if isinstance(value, list) and len(value) == 6:
        return tuple(float(component) for component in value)
    return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _compute_primitives_bbox(primitives: Iterable[dict[str, Any]]) -> Rect | None:
    points: list[Point] = []
    for primitive in primitives:
        primitive_type = primitive.get("type")
        attributes = primitive.get("attributes", {})
        transform_tuple = _normalize_transform_tuple(primitive.get("transform"))
        if primitive_type in {"rect", "image"}:
            try:
                x = float(attributes.get("x", 0.0) or 0.0)
                y = float(attributes.get("y", 0.0) or 0.0)
                width = float(attributes.get("width", 0.0) or 0.0)
                height = float(attributes.get("height", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            corners = [
                Point(x, y),
                Point(x + width, y),
                Point(x + width, y + height),
                Point(x, y + height),
            ]
            points.extend(_transform_point(corner, transform_tuple) for corner in corners)
    if not points:
        return None
    min_x = min(point.x for point in points)
    max_x = max(point.x for point in points)
    min_y = min(point.y for point in points)
    max_y = max(point.y for point in points)
    return Rect(
        x=min_x,
        y=min_y,
        width=max_x - min_x,
        height=max_y - min_y,
    )


def _matrix_to_tuple(matrix: ResvgMatrix | None) -> Tuple[float, float, float, float, float, float]:
    if matrix is None:
        return (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    return (matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f)


def _matrix_to_matrix2d(matrix: ResvgMatrix | None) -> Matrix2D:
    tuple_matrix = _matrix_to_tuple(matrix)
    return Matrix2D(
        a=tuple_matrix[0],
        b=tuple_matrix[1],
        c=tuple_matrix[2],
        d=tuple_matrix[3],
        e=tuple_matrix[4],
        f=tuple_matrix[5],
    )


def _combine_transform(
    parent: ResvgMatrix,
    child: ResvgMatrix | None,
) -> ResvgMatrix:
    if child is None:
        return parent
    return parent.multiply(child)


def _parse_region(attributes: Dict[str, Any]) -> Rect | None:
    try:
        x = float(attributes.get("x", 0.0) or 0.0)
        y = float(attributes.get("y", 0.0) or 0.0)
        width = float(attributes.get("width", 0.0) or 0.0)
        height = float(attributes.get("height", 0.0) or 0.0)
        return Rect(x=x, y=y, width=width, height=height)
    except (TypeError, ValueError):
        return None


def _normalize_mask_mode(mask_type: str | None) -> str | None:
    if mask_type is None:
        return None
    lowered = mask_type.lower()
    if lowered in {"alpha", "luminance"}:
        return lowered
    return mask_type


def _serialize_source(node: BaseNode) -> str | None:
    source = getattr(node, "source", None)
    if source is None:
        return None
    try:
        return source.tostring()  # type: ignore[attr-defined]
    except Exception:
        return None


__all__ = ["collect_resvg_clip_definitions", "collect_resvg_mask_info"]
