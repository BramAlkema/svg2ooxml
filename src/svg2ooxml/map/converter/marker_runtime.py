"""Marker rendering helpers extracted from the IR converter."""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from lxml import etree

from svg2ooxml.geometry.paths.parser import parse_path_data
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType
from svg2ooxml.ir.paint import GradientPaintRef, PatternPaint, SolidPaint, Stroke
from svg2ooxml.ir.scene import Path
from svg2ooxml.map.converter.markers import (
    MarkerInstance,
    apply_local_transform,
    build_marker_transform,
)
from svg2ooxml.parser.geometry import Matrix2D
from svg2ooxml.policy.constants import FALLBACK_BITMAP


def apply_marker_metadata(converter, element: etree._Element, metadata: dict[str, Any]) -> None:
    if metadata is None:
        return

    markers: dict[str, str] = {}

    def record_marker(raw_value: str | None, key: str) -> None:
        if not raw_value:
            return
        marker_id = converter._normalize_href_reference(raw_value)
        if marker_id:
            markers[key] = marker_id

    record_marker(element.get("marker-start"), "start")
    record_marker(element.get("marker-mid"), "mid")
    record_marker(element.get("marker-end"), "end")

    style_attr = element.get("style")
    if style_attr:
        for chunk in style_attr.split(";"):
            if ":" not in chunk:
                continue
            name, value = chunk.split(":", 1)
            name = name.strip()
            if name in {"marker-start", "marker-mid", "marker-end"}:
                record_marker(value.strip(), name.split("-")[-1])

    if markers:
        existing = metadata.setdefault("markers", {})
        for key, value in markers.items():
            existing.setdefault(key, value)
        usage_bucket = getattr(converter, "_marker_usage", None)
        if isinstance(usage_bucket, set):
            usage_bucket.update(markers.values())
        trace_stage = getattr(converter, "_trace_stage", None)
        if callable(trace_stage):
            trace_stage(
                "marker_detected",
                stage="marker",
                metadata={"markers": dict(markers)},
            )


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

    start_anchor = _compute_marker_anchor(segments, position="start", tolerance=tolerance)
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
    if clip_rect:
        metadata_seed["marker_clip"] = {
            "x": clip_rect[0],
            "y": clip_rect[1],
            "width": clip_rect[2],
            "height": clip_rect[3],
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

    segment_total = sum(len(getattr(shape, "segments", []) or []) for shape in marker_shapes)
    policy_meta: dict[str, Any] | None = None

    marker_policy = converter._policy_options("marker") or converter._policy_options("geometry")
    if marker_policy:
        force_bitmap = bool(marker_policy.get("force_bitmap"))
        max_segments = marker_policy.get("max_segments")
        if force_bitmap or (isinstance(max_segments, (int, float)) and segment_total > max_segments):
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

    transformed_segments = converter._transform_segments(segments, combined_matrix)
    style = converter._style_extractor.extract(element, converter._services, context=converter._css_context)
    fill, stroke = _resolve_marker_paints(
        element=element,
        style=style,
        base_style=base_style,
        instance=instance,
    )

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

    return [marker_path]


def _expand_marker_use(converter, element: etree._Element) -> list[etree._Element]:
    href_attr = element.get("{http://www.w3.org/1999/xlink}href") or element.get("href")
    reference_id = converter._normalize_href_reference(href_attr)
    if reference_id is None:
        return []

    target = converter._symbol_definitions.get(reference_id)
    if target is None:
        target = converter._element_index.get(reference_id)
    if target is None:
        return []

    clones = converter._instantiate_use_target(target, element)
    transform_matrix = converter._compute_use_transform(element, target)
    dx, dy = converter._resolve_use_offsets(element)
    converter._apply_use_transform(clones, transform_matrix, dx, dy)
    return clones


def _marker_segments_for_element(element: etree._Element, local_name: str) -> list[SegmentType]:
    if local_name == "path":
        path_data = element.get("d")
        if not path_data:
            return []
        try:
            return list(parse_path_data(path_data))
        except Exception:
            return []

    if local_name == "line":
        x1 = _parse_float(element.get("x1"))
        y1 = _parse_float(element.get("y1"))
        x2 = _parse_float(element.get("x2"))
        y2 = _parse_float(element.get("y2"))
        if None in (x1, y1, x2, y2):
            return []
        return [LineSegment(Point(x1, y1), Point(x2, y2))]

    if local_name in {"polyline", "polygon"}:
        points = _parse_points(element.get("points"))
        if len(points) < 2:
            return []
        return _points_to_segments(points, closed=local_name == "polygon")

    if local_name == "rect":
        width = _parse_float(element.get("width"))
        height = _parse_float(element.get("height"))
        if width is None or height is None or width <= 0 or height <= 0:
            return []
        x = _parse_float(element.get("x"), default=0.0) or 0.0
        y = _parse_float(element.get("y"), default=0.0) or 0.0
        return _rect_segments(x, y, width, height)

    if local_name == "circle":
        radius = _parse_float(element.get("r"))
        if radius is None or radius <= 0:
            return []
        cx = _parse_float(element.get("cx"), default=0.0) or 0.0
        cy = _parse_float(element.get("cy"), default=0.0) or 0.0
        return _ellipse_segments(cx, cy, radius, radius)

    if local_name == "ellipse":
        rx = _parse_float(element.get("rx"))
        ry = _parse_float(element.get("ry"))
        if rx is None or ry is None or rx <= 0 or ry <= 0:
            return []
        cx = _parse_float(element.get("cx"), default=0.0) or 0.0
        cy = _parse_float(element.get("cy"), default=0.0) or 0.0
        return _ellipse_segments(cx, cy, rx, ry)

    return []


def _resolve_marker_paints(
    *,
    element: etree._Element,
    style,
    base_style: dict[str, Any],
    instance: MarkerInstance,
) -> tuple[SolidPaint | GradientPaintRef | PatternPaint | None, Stroke | None]:
    fill = style.fill
    stroke = style.stroke

    child_fill_attr = (element.get("fill") or "").strip()
    child_stroke_attr = (element.get("stroke") or "").strip()

    stroke_paint = base_style.get("stroke")
    fill_paint = base_style.get("fill")

    if child_fill_attr == "context-stroke" and stroke_paint is not None:
        fill = stroke_paint
    elif child_fill_attr == "context-fill" and fill_paint is not None:
        fill = fill_paint

    if child_stroke_attr == "context-stroke" and stroke_paint is not None:
        if isinstance(stroke_paint, SolidPaint):
            stroke = Stroke(paint=stroke_paint, width=instance.stroke_width)
    elif child_stroke_attr == "context-fill" and fill_paint is not None:
        if isinstance(fill_paint, SolidPaint):
            stroke = Stroke(paint=fill_paint, width=instance.stroke_width)

    return fill, stroke


def _compute_marker_anchor(
    segments: list[SegmentType],
    *,
    position: str,
    tolerance: float,
) -> tuple[Point, float] | None:
    if not segments:
        return None

    if position == "start":
        segment = segments[0]
        start_point = getattr(segment, "start", None)
        vector = _segment_tangent(segment, at_end=False)
    elif position == "end":
        segment = segments[-1]
        start_point = getattr(segment, "end", None)
        vector = _segment_tangent(segment, at_end=True)
    else:
        return None

    if start_point is None or vector is None:
        return None

    if abs(vector.x) <= tolerance and abs(vector.y) <= tolerance:
        return None

    angle = math.degrees(math.atan2(vector.y, vector.x))
    return Point(start_point.x, start_point.y), angle


def _compute_mid_markers(
    segments: list[SegmentType],
    *,
    tolerance: float,
) -> list[tuple[Point, float]]:
    anchors: list[tuple[Point, float]] = []
    if len(segments) < 2:
        return anchors
    for idx in range(1, len(segments)):
        prev_seg = segments[idx - 1]
        curr_seg = segments[idx]
        joint = getattr(curr_seg, "start", None)
        if joint is None:
            continue
        incoming = _segment_tangent(prev_seg, at_end=True)
        outgoing = _segment_tangent(curr_seg, at_end=False)
        if incoming is None or outgoing is None:
            continue
        vec_x = incoming.x + outgoing.x
        vec_y = incoming.y + outgoing.y
        if abs(vec_x) < tolerance and abs(vec_y) < tolerance:
            vec_x, vec_y = outgoing.x, outgoing.y
        angle = math.degrees(math.atan2(vec_x if vec_x != 0 else vec_y, vec_y if vec_x != 0 else vec_x))
        # Adjust angle calculation: we actually want atan2 on (vec_y, vec_x).
        angle = math.degrees(math.atan2(vec_y, vec_x))
        anchors.append((Point(joint.x, joint.y), angle))
    return anchors


def _segment_tangent(segment: SegmentType, *, at_end: bool) -> Point | None:
    if isinstance(segment, LineSegment):
        if at_end:
            return Point(segment.end.x - segment.start.x, segment.end.y - segment.start.y)
        return Point(segment.end.x - segment.start.x, segment.end.y - segment.start.y)
    if isinstance(segment, BezierSegment):
        if at_end:
            return Point(segment.end.x - segment.control2.x, segment.end.y - segment.control2.y)
        return Point(segment.control1.x - segment.start.x, segment.control1.y - segment.start.y)
    start = getattr(segment, "start", None)
    end = getattr(segment, "end", None)
    if start is None or end is None:
        return None
    return Point(end.x - start.x, end.y - start.y)


def _parse_float(value: str | None, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _parse_points(value: str | None) -> list[Point]:
    if not value:
        return []
    parts = value.replace(",", " ").split()
    points: list[Point] = []
    iterator = iter(parts)
    for x_str, y_str in zip(iterator, iterator):
        try:
            x = float(x_str)
            y = float(y_str)
        except ValueError:
            continue
        points.append(Point(x, y))
    return points


def _points_to_segments(points: list[Point], *, closed: bool) -> list[SegmentType]:
    segments: list[SegmentType] = []
    for idx in range(1, len(points)):
        segments.append(LineSegment(points[idx - 1], points[idx]))
    if closed and points:
        segments.append(LineSegment(points[-1], points[0]))
    return segments


def _rect_segments(x: float, y: float, width: float, height: float) -> list[SegmentType]:
    top_left = Point(x, y)
    top_right = Point(x + width, y)
    bottom_right = Point(x + width, y + height)
    bottom_left = Point(x, y + height)
    return [
        LineSegment(top_left, top_right),
        LineSegment(top_right, bottom_right),
        LineSegment(bottom_right, bottom_left),
        LineSegment(bottom_left, top_left),
    ]


def _ellipse_segments(cx: float, cy: float, rx: float, ry: float) -> list[SegmentType]:
    if rx <= 0 or ry <= 0:
        return []
    kappa = 0.5522847498307936
    top = Point(cx, cy - ry)
    right = Point(cx + rx, cy)
    bottom = Point(cx, cy + ry)
    left = Point(cx - rx, cy)

    return [
        BezierSegment(
            start=right,
            control1=Point(cx + rx, cy + kappa * ry),
            control2=Point(cx + kappa * rx, cy + ry),
            end=bottom,
        ),
        BezierSegment(
            start=bottom,
            control1=Point(cx - kappa * rx, cy + ry),
            control2=Point(cx - rx, cy + kappa * ry),
            end=left,
        ),
        BezierSegment(
            start=left,
            control1=Point(cx - rx, cy - kappa * ry),
            control2=Point(cx - kappa * rx, cy - ry),
            end=top,
        ),
        BezierSegment(
            start=top,
            control1=Point(cx + kappa * rx, cy - ry),
            control2=Point(cx + rx, cy - kappa * ry),
            end=right,
        ),
    ]


__all__ = ["apply_marker_metadata", "build_marker_shapes"]
