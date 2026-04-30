"""Marker rendering helpers extracted from the IR converter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.core.styling.style_runtime import extract_style
from svg2ooxml.core.traversal.marker_geometry import (
    compute_marker_anchor as _compute_marker_anchor,
)
from svg2ooxml.core.traversal.marker_geometry import (
    compute_mid_markers as _compute_mid_markers,
)
from svg2ooxml.core.traversal.marker_geometry import (
    expand_marker_use as _expand_marker_use,
)
from svg2ooxml.core.traversal.marker_geometry import (
    marker_segments_for_element as _marker_segments_for_element,
)
from svg2ooxml.core.traversal.marker_metadata import apply_marker_metadata
from svg2ooxml.core.traversal.markers import (
    MarkerDefinition,
    MarkerInstance,
    apply_local_transform,
    build_marker_transform,
)
from svg2ooxml.ir.geometry import LineSegment, Point, Rect, SegmentType
from svg2ooxml.ir.paint import GradientPaintRef, PatternPaint, SolidPaint, Stroke
from svg2ooxml.ir.scene import Path
from svg2ooxml.policy.constants import FALLBACK_BITMAP


def build_marker_shapes(
    converter,
    element: etree._Element,
    path: Path,
    *,
    tolerance: float,
) -> list[Path]:
    metadata = path.metadata if isinstance(path.metadata, dict) else {}
    markers_meta = metadata.get("markers") if isinstance(metadata, dict) else None
    if not markers_meta:
        return []

    marker_service = getattr(converter._services, "marker_service", None)
    if marker_service is None:
        return []

    segments = list(path.segments)
    if not segments:
        return []

    stroke_width = 1.0
    if path.stroke and path.stroke.width is not None:
        try:
            stroke_width = max(float(path.stroke.width), tolerance)
        except (TypeError, ValueError):
            stroke_width = 1.0

    instances = _collect_marker_instances(
        converter=converter,
        markers_meta=markers_meta,
        marker_service=marker_service,
        segments=segments,
        stroke_width=stroke_width,
        tolerance=tolerance,
    )
    if not instances:
        return []

    base_style = {
        "fill": path.fill,
        "stroke": path.stroke.paint if path.stroke else None,
    }

    shapes: list[Path] = []
    for instance in instances:
        shapes.extend(
            _realize_marker_instance(
                converter=converter,
                source_element=element,
                instance=instance,
                base_style=base_style,
                parent_path=path,
                tolerance=tolerance,
            )
        )
    trace_stage = getattr(converter, "_trace_stage", None)
    if callable(trace_stage) and shapes:
        marker_ids = sorted(
            {
                getattr(instance.definition, "marker_id", None)
                for instance in instances
                if getattr(instance.definition, "marker_id", None)
            }
        )
        trace_stage(
            "marker_shapes_generated",
            stage="marker",
            metadata={"count": len(shapes), "marker_ids": marker_ids},
        )
    return shapes


def _collect_marker_instances(
    *,
    converter,
    markers_meta: dict[str, str],
    marker_service,
    segments: list[SegmentType],
    stroke_width: float,
    tolerance: float,
) -> list[MarkerInstance]:
    instances: list[MarkerInstance] = []

    start_anchor = _compute_marker_anchor(
        segments, position="start", tolerance=tolerance
    )
    end_anchor = _compute_marker_anchor(segments, position="end", tolerance=tolerance)
    mid_anchors = _compute_mid_markers(segments, tolerance=tolerance)

    if "start" in markers_meta and start_anchor is not None:
        definition = marker_service.get_definition(markers_meta["start"])
        if definition is not None:
            anchor_point, angle = start_anchor
            instances.append(
                MarkerInstance(
                    definition=definition,
                    position="start",
                    anchor=anchor_point,
                    angle=angle,
                    stroke_width=stroke_width,
                )
            )

    if "end" in markers_meta and end_anchor is not None:
        definition = marker_service.get_definition(markers_meta["end"])
        if definition is not None:
            anchor_point, angle = end_anchor
            instances.append(
                MarkerInstance(
                    definition=definition,
                    position="end",
                    anchor=anchor_point,
                    angle=angle,
                    stroke_width=stroke_width,
                )
            )

    if "mid" in markers_meta and mid_anchors:
        definition = marker_service.get_definition(markers_meta["mid"])
        if definition is not None:
            for anchor_point, angle in mid_anchors:
                instances.append(
                    MarkerInstance(
                        definition=definition,
                        position="mid",
                        anchor=anchor_point,
                        angle=angle,
                        stroke_width=stroke_width,
                    )
                )

    return instances


def _realize_marker_instance(
    *,
    converter,
    source_element: etree._Element,
    instance: MarkerInstance,
    base_style: dict[str, Any],
    parent_path: Path,
    tolerance: float,
) -> list[Path]:
    transform = build_marker_transform(
        definition=instance.definition,
        anchor=instance.anchor,
        angle=instance.angle,
        stroke_width=instance.stroke_width,
        position=instance.position,
    )
    matrix = transform.matrix

    overflow = instance.definition.overflow
    clip_rect = transform.clip_rect

    parent_ids: list[str] = []
    if isinstance(parent_path.metadata, dict):
        ids = parent_path.metadata.get("element_ids", [])
        if isinstance(ids, list):
            parent_ids = [str(item) for item in ids]

    marker_shapes: list[Path] = []

    metadata_seed: dict[str, Any] = {
        "source": "marker",
        "marker_id": instance.definition.marker_id,
        "marker_position": instance.position,
        "source_element": source_element,
    }
    clip_bounds = None
    if clip_rect:
        metadata_seed["marker_clip"] = {
            "x": clip_rect[0],
            "y": clip_rect[1],
            "width": clip_rect[2],
            "height": clip_rect[3],
        }
        clip_bounds = _transformed_marker_clip_bounds(matrix, instance.definition)
        if clip_bounds is not None:
            metadata_seed["marker_clip_bounds"] = {
                "x": clip_bounds.x,
                "y": clip_bounds.y,
                "width": clip_bounds.width,
                "height": clip_bounds.height,
            }
    if instance.definition.viewbox is not None:
        viewbox = instance.definition.viewbox
        metadata_seed["marker_viewbox"] = {
            "min_x": viewbox.min_x,
            "min_y": viewbox.min_y,
            "width": viewbox.width,
            "height": viewbox.height,
        }
    if overflow:
        metadata_seed["marker_overflow"] = overflow
    if parent_ids:
        metadata_seed["parent_path_ids"] = parent_ids

    for child in instance.definition.element:
        marker_shapes.extend(
            _convert_marker_node(
                converter=converter,
                element=child,
                matrix=matrix,
                instance=instance,
                base_style=base_style,
                source_element=source_element,
                metadata_seed=metadata_seed,
                tolerance=tolerance,
            )
        )

    if not marker_shapes:
        return []

    segment_total = sum(
        len(getattr(shape, "segments", []) or []) for shape in marker_shapes
    )
    policy_meta: dict[str, Any] | None = None

    marker_policy = converter._policy_options("marker") or converter._policy_options(
        "geometry"
    )
    if marker_policy:
        force_bitmap = bool(marker_policy.get("force_bitmap"))
        allow_bitmap = (
            bool(marker_policy.get("allow_bitmap_fallback", True)) or force_bitmap
        )
        max_segments = marker_policy.get("max_segments")
        if allow_bitmap and (
            force_bitmap
            or (isinstance(max_segments, (int, float)) and segment_total > max_segments)
        ):
            policy_meta = {
                "render_mode": FALLBACK_BITMAP,
                "reason": "marker_complexity",
                "segment_count": segment_total,
            }

    if policy_meta:
        metadata_seed["policy"] = {
            "marker": {
                **policy_meta,
                "stroke_width": instance.stroke_width,
                "path_angle": instance.angle,
            }
        }

    return marker_shapes


def _convert_marker_node(
    *,
    converter,
    element: etree._Element,
    matrix: Matrix2D,
    instance: MarkerInstance,
    base_style: dict[str, Any],
    source_element: etree._Element,
    metadata_seed: Mapping[str, Any],
    tolerance: float,
) -> list[Path]:
    local = converter._local_name(element.tag)
    if not local:
        return []

    combined_matrix = apply_local_transform(matrix, element.get("transform"))

    if local == "g":
        shapes: list[Path] = []
        for child in element:
            shapes.extend(
                _convert_marker_node(
                    converter=converter,
                    element=child,
                    matrix=combined_matrix,
                    instance=instance,
                    base_style=base_style,
                    source_element=source_element,
                    metadata_seed=metadata_seed,
                    tolerance=tolerance,
                )
            )
        return shapes

    if local == "use":
        referenced = _expand_marker_use(converter, element)
        shapes: list[Path] = []
        for expanded in referenced:
            shapes.extend(
                _convert_marker_node(
                    converter=converter,
                    element=expanded,
                    matrix=combined_matrix,
                    instance=instance,
                    base_style=base_style,
                    source_element=source_element,
                    metadata_seed=metadata_seed,
                    tolerance=tolerance,
                )
            )
        return shapes

    segments = _marker_segments_for_element(element, local)
    if not segments:
        return []

    style = extract_style(converter, element)
    fill, stroke = _resolve_marker_paints(
        element=element,
        style=style,
        base_style=base_style,
        instance=instance,
    )
    transformed_segments = converter._transform_segments(segments, combined_matrix)
    transformed_segments = _clip_marker_segments(
        transformed_segments,
        metadata_seed,
        has_fill=fill is not None,
        tolerance=tolerance,
    )
    if not transformed_segments:
        return []

    clip_ref = converter._resolve_clip_ref(element)
    mask_ref, mask_instance = converter._resolve_mask_ref(element)

    metadata: dict[str, Any] = {}
    if metadata_seed:
        metadata.update(metadata_seed)

    style_metadata = dict(style.metadata)
    style_policy = style_metadata.pop("policy", None)
    seed_policy = metadata.pop("policy", None)
    metadata.update(style_metadata)

    if seed_policy or style_policy:
        merged_policy: dict[str, Any] = {}
        if isinstance(style_policy, dict):
            merged_policy.update(style_policy)
        if isinstance(seed_policy, dict):
            for key, value in seed_policy.items():
                if (
                    key in merged_policy
                    and isinstance(merged_policy[key], dict)
                    and isinstance(value, Mapping)
                ):
                    combined = dict(merged_policy[key])
                    combined.update(value)
                    merged_policy[key] = combined
                else:
                    merged_policy[key] = value
        metadata["policy"] = merged_policy

    marker_path = Path(
        segments=transformed_segments,
        fill=fill,
        stroke=stroke or style.stroke,
        clip=clip_ref,
        mask=mask_ref,
        mask_instance=mask_instance,
        opacity=style.opacity,
        transform=None,
        effects=list(style.effects),
        metadata=metadata,
    )
    converter._process_mask_metadata(marker_path)
    converter._trace_geometry_decision(source_element, "marker", marker_path.metadata)
    return [marker_path]


def _transformed_marker_clip_bounds(
    matrix: Matrix2D,
    definition: MarkerDefinition,
) -> Rect | None:
    if definition.viewbox is not None:
        x = definition.viewbox.min_x
        y = definition.viewbox.min_y
        width = definition.viewbox.width
        height = definition.viewbox.height
    else:
        x = 0.0
        y = 0.0
        width = definition.marker_width
        height = definition.marker_height
    if width <= 0.0 or height <= 0.0:
        return None
    points = [
        matrix.transform_point(Point(x, y)),
        matrix.transform_point(Point(x + width, y)),
        matrix.transform_point(Point(x + width, y + height)),
        matrix.transform_point(Point(x, y + height)),
    ]
    min_x = min(point.x for point in points)
    min_y = min(point.y for point in points)
    max_x = max(point.x for point in points)
    max_y = max(point.y for point in points)
    if max_x <= min_x or max_y <= min_y:
        return None
    return Rect(min_x, min_y, max_x - min_x, max_y - min_y)


def _clip_marker_segments(
    segments: list[SegmentType],
    metadata_seed: Mapping[str, Any],
    *,
    has_fill: bool,
    tolerance: float,
) -> list[SegmentType]:
    if not has_fill:
        return segments
    if metadata_seed.get("marker_overflow") != "hidden":
        return segments
    raw_bounds = metadata_seed.get("marker_clip_bounds")
    if not isinstance(raw_bounds, Mapping):
        return segments
    clip_bounds = _rect_from_mapping(raw_bounds)
    if clip_bounds is None:
        return segments

    polygon = _closed_line_polygon(segments, tolerance=tolerance)
    if polygon is None:
        return segments
    clipped = _clip_polygon_to_rect(polygon, clip_bounds)
    if len(clipped) < 3:
        return []
    return _polygon_to_segments(clipped)


def _rect_from_mapping(raw: Mapping[str, Any]) -> Rect | None:
    try:
        x = float(raw["x"])
        y = float(raw["y"])
        width = float(raw["width"])
        height = float(raw["height"])
    except (KeyError, TypeError, ValueError):
        return None
    if width <= 0.0 or height <= 0.0:
        return None
    return Rect(x, y, width, height)


def _closed_line_polygon(
    segments: list[SegmentType],
    *,
    tolerance: float,
) -> list[Point] | None:
    if not segments or not all(
        isinstance(segment, LineSegment) for segment in segments
    ):
        return None
    points = [segments[0].start]
    previous = segments[0].start
    for segment in segments:
        if _point_distance(previous, segment.start) > tolerance:
            return None
        points.append(segment.end)
        previous = segment.end
    if len(points) < 4 or _point_distance(points[0], points[-1]) > tolerance:
        return None
    return points[:-1]


def _clip_polygon_to_rect(points: list[Point], clip: Rect) -> list[Point]:
    clipped = points
    for edge in ("left", "right", "top", "bottom"):
        if not clipped:
            return []
        clipped = _clip_polygon_edge(clipped, clip, edge)
    return clipped


def _clip_polygon_edge(points: list[Point], clip: Rect, edge: str) -> list[Point]:
    output: list[Point] = []
    previous = points[-1]
    previous_inside = _inside_clip_edge(previous, clip, edge)
    for current in points:
        current_inside = _inside_clip_edge(current, clip, edge)
        if current_inside:
            if not previous_inside:
                output.append(_intersect_clip_edge(previous, current, clip, edge))
            output.append(current)
        elif previous_inside:
            output.append(_intersect_clip_edge(previous, current, clip, edge))
        previous = current
        previous_inside = current_inside
    return output


def _inside_clip_edge(point: Point, clip: Rect, edge: str) -> bool:
    if edge == "left":
        return point.x >= clip.left
    if edge == "right":
        return point.x <= clip.right
    if edge == "top":
        return point.y >= clip.top
    return point.y <= clip.bottom


def _intersect_clip_edge(start: Point, end: Point, clip: Rect, edge: str) -> Point:
    dx = end.x - start.x
    dy = end.y - start.y
    if edge in {"left", "right"}:
        x = clip.left if edge == "left" else clip.right
        if abs(dx) <= 1e-12:
            return Point(x, start.y)
        t = (x - start.x) / dx
        return Point(x, start.y + t * dy)

    y = clip.top if edge == "top" else clip.bottom
    if abs(dy) <= 1e-12:
        return Point(start.x, y)
    t = (y - start.y) / dy
    return Point(start.x + t * dx, y)


def _polygon_to_segments(points: list[Point]) -> list[SegmentType]:
    return [
        LineSegment(start=start, end=end)
        for start, end in zip(points, [*points[1:], points[0]], strict=True)
    ]


def _point_distance(a: Point, b: Point) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    return (dx * dx + dy * dy) ** 0.5


def _resolve_marker_paints(
    *,
    element: etree._Element,
    style,
    base_style: Mapping[str, Any],
    instance: MarkerInstance,
) -> tuple[Any, Stroke | None]:
    fill = style.fill
    stroke = style.stroke

    fill_attr = element.get("fill")
    if fill_attr:
        token = fill_attr.strip().lower()
        if token == "context-stroke" and isinstance(
            base_style.get("stroke"), SolidPaint
        ):
            fill = base_style["stroke"]
        elif token == "context-fill" and isinstance(base_style.get("fill"), SolidPaint):
            fill = base_style["fill"]

    stroke_attr = element.get("stroke")
    if stroke_attr:
        token = stroke_attr.strip().lower()
        if token == "context-fill" and isinstance(base_style.get("fill"), SolidPaint):
            stroke = Stroke(
                paint=base_style["fill"],
                width=style.stroke.width if style.stroke else instance.stroke_width,
                join=style.stroke.join if style.stroke else None,
                cap=style.stroke.cap if style.stroke else None,
                miter_limit=style.stroke.miter_limit if style.stroke else 4.0,
                dash_array=style.stroke.dash_array if style.stroke else None,
                dash_offset=style.stroke.dash_offset if style.stroke else 0.0,
                opacity=style.stroke.opacity if style.stroke else 1.0,
            )

    if isinstance(fill, GradientPaintRef) and isinstance(
        base_style.get("fill"), SolidPaint
    ):
        fill = base_style["fill"]
    if isinstance(fill, PatternPaint) and isinstance(
        base_style.get("fill"), SolidPaint
    ):
        fill = base_style["fill"]

    if stroke is None and isinstance(base_style.get("stroke"), SolidPaint):
        stroke = Stroke(
            paint=base_style["stroke"],
            width=instance.stroke_width,
            join=style.stroke.join if style.stroke else None,
            cap=style.stroke.cap if style.stroke else None,
            miter_limit=style.stroke.miter_limit if style.stroke else 4.0,
            dash_array=style.stroke.dash_array if style.stroke else None,
            dash_offset=style.stroke.dash_offset if style.stroke else 0.0,
            opacity=style.stroke.opacity if style.stroke else 1.0,
        )

    return fill, stroke


__all__ = ["apply_marker_metadata", "build_marker_shapes"]
