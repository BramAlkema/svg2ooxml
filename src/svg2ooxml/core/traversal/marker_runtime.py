"""Marker rendering helpers extracted from the IR converter."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from lxml import etree

from svg2ooxml.common.conversions.transforms import parse_numeric_list
from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.common.geometry.paths import parse_path_data
from svg2ooxml.common.style.css_values import parse_style_declarations
from svg2ooxml.common.svg_refs import local_url_id
from svg2ooxml.core.styling.style_runtime import extract_style
from svg2ooxml.core.traversal.markers import (
    MarkerDefinition,
    MarkerInstance,
    apply_local_transform,
    build_marker_transform,
)
from svg2ooxml.core.traversal.runtime import local_name as _local_name
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType
from svg2ooxml.ir.paint import GradientPaintRef, PatternPaint, SolidPaint, Stroke
from svg2ooxml.ir.scene import Path
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
    for name, value in parse_style_declarations(style_attr)[0].items():
        if name in {"marker-start", "marker-mid", "marker-end"}:
            record_marker(value, name.split("-")[-1])

    if markers:
        existing = metadata.setdefault("markers", {})
        for key, value in markers.items():
            existing.setdefault(key, value)
        profiles = _build_marker_profiles(converter, markers)
        if profiles:
            existing_profiles = metadata.setdefault("marker_profiles", {})
            if isinstance(existing_profiles, dict):
                for key, value in profiles.items():
                    existing_profiles.setdefault(key, value)
        usage_bucket = getattr(converter, "_marker_usage", None)
        if isinstance(usage_bucket, set):
            usage_bucket.update(markers.values())
        trace_stage = getattr(converter, "_trace_stage", None)
        if callable(trace_stage):
            trace_stage(
                "marker_detected",
                stage="marker",
                metadata={"markers": dict(markers), "marker_profiles": dict(profiles)},
            )


def _build_marker_profiles(converter, markers: Mapping[str, str]) -> dict[str, dict[str, str]]:
    services = getattr(converter, "_services", None)
    marker_service = getattr(services, "marker_service", None)
    if marker_service is None:
        return {}

    profiles: dict[str, dict[str, str]] = {}
    for position, marker_id in markers.items():
        definition = marker_service.get_definition(marker_id)
        profile = _profile_from_marker_definition(definition)
        if profile:
            profiles[position] = profile
    return profiles


def _profile_from_marker_definition(definition: MarkerDefinition | None) -> dict[str, str] | None:
    if definition is None:
        return None
    marker_type = _classify_marker_type(definition.element)
    if marker_type is None:
        return None
    size = _classify_marker_size(definition)
    return {"type": marker_type, "size": size, "source": "geometry"}


def _classify_marker_size(definition: MarkerDefinition) -> str:
    extent = max(float(definition.marker_width), float(definition.marker_height))
    if definition.viewbox is not None:
        extent = max(extent, float(definition.viewbox.width), float(definition.viewbox.height))
    if extent <= 2.0:
        return "sm"
    if extent >= 8.0:
        return "lg"
    return "med"


def _classify_marker_type(marker_element: etree._Element) -> str | None:
    candidates: list[tuple[int, str]] = []
    for node in marker_element.iter():
        tag = _local_name(node.tag)
        if tag in {"circle", "ellipse"}:
            return "oval"
        points = _extract_points_for_classification(node, tag)
        if len(points) < 3:
            continue
        if _looks_like_diamond(points):
            candidates.append((80, "diamond"))
            continue
        if _looks_like_arrow(points):
            candidates.append((70, "arrow"))
            continue
        if len(points) == 3:
            candidates.append((60, "triangle"))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _extract_points_for_classification(node: etree._Element, local_name: str) -> list[tuple[float, float]]:
    if local_name == "path":
        path_data = node.get("d")
        if not path_data:
            return []
        try:
            segments = parse_path_data(path_data)
        except Exception:
            return []
        points: list[tuple[float, float]] = []
        for segment in segments:
            if isinstance(segment, LineSegment):
                points.append((segment.start.x, segment.start.y))
                points.append((segment.end.x, segment.end.y))
            elif isinstance(segment, BezierSegment):
                # Endpoints are sufficient for coarse marker archetype detection.
                points.append((segment.start.x, segment.start.y))
                points.append((segment.end.x, segment.end.y))
        return _dedupe_points(points)
    if local_name in {"polygon", "polyline"}:
        points_attr = node.get("points") or ""
        values = parse_numeric_list(points_attr)
        if len(values) < 6:
            return []
        points = [(values[i], values[i + 1]) for i in range(0, len(values) - 1, 2)]
        return _dedupe_points(points)
    return []


def _dedupe_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    ordered: list[tuple[float, float]] = []
    seen: set[tuple[int, int]] = set()
    for x, y in points:
        key = (int(round(x * 1000)), int(round(y * 1000)))
        if key in seen:
            continue
        seen.add(key)
        ordered.append((x, y))
    return ordered


def _looks_like_diamond(points: list[tuple[float, float]]) -> bool:
    if len(points) != 4:
        return False
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x
    height = max_y - min_y
    if width <= 1e-6 or height <= 1e-6:
        return False
    mid_x = min_x + width * 0.5
    mid_y = min_y + height * 0.5
    tol_x = width * 0.2
    tol_y = height * 0.2

    def _near(value: float, target: float, tolerance: float) -> bool:
        return abs(value - target) <= tolerance

    has_left = any(_near(x, min_x, tol_x) and _near(y, mid_y, tol_y) for x, y in points)
    has_right = any(_near(x, max_x, tol_x) and _near(y, mid_y, tol_y) for x, y in points)
    has_top = any(_near(y, min_y, tol_y) and _near(x, mid_x, tol_x) for x, y in points)
    has_bottom = any(_near(y, max_y, tol_y) and _near(x, mid_x, tol_x) for x, y in points)
    return has_left and has_right and has_top and has_bottom


def _looks_like_arrow(points: list[tuple[float, float]]) -> bool:
    if len(points) < 4:
        return False
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    if width <= 1e-6 or height <= 1e-6:
        return False
    return _has_arrow_profile(xs) or _has_arrow_profile(ys)


def _has_arrow_profile(coords: list[float]) -> bool:
    min_coord = min(coords)
    max_coord = max(coords)
    span = max_coord - min_coord
    if span <= 1e-6:
        return False
    tip_tol = span * 0.1
    rear_tol = span * 0.2
    inner_min = min_coord + span * 0.2
    inner_max = min_coord + span * 0.8

    tip_low = sum(1 for coord in coords if abs(coord - min_coord) <= tip_tol)
    tip_high = sum(1 for coord in coords if abs(coord - max_coord) <= tip_tol)
    rear_low = sum(1 for coord in coords if abs(coord - min_coord) <= rear_tol)
    rear_high = sum(1 for coord in coords if abs(coord - max_coord) <= rear_tol)
    inner = sum(1 for coord in coords if inner_min < coord < inner_max)

    if tip_high == 1 and rear_low >= 2 and inner >= 1:
        return True
    if tip_low == 1 and rear_high >= 2 and inner >= 1:
        return True
    return False


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
        allow_bitmap = bool(marker_policy.get("allow_bitmap_fallback", True)) or force_bitmap
        max_segments = marker_policy.get("max_segments")
        if allow_bitmap and (force_bitmap or (isinstance(max_segments, (int, float)) and segment_total > max_segments)):
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
    style = extract_style(converter, element)
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
    converter._process_mask_metadata(marker_path)
    converter._trace_geometry_decision(source_element, "marker", marker_path.metadata)
    return [marker_path]


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
        if token == "context-stroke" and isinstance(base_style.get("stroke"), SolidPaint):
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

    if isinstance(fill, GradientPaintRef) and isinstance(base_style.get("fill"), SolidPaint):
        fill = base_style["fill"]
    if isinstance(fill, PatternPaint) and isinstance(base_style.get("fill"), SolidPaint):
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


def _marker_segments_for_element(element: etree._Element, local_name: str) -> list[SegmentType]:
    if local_name == "path":
        d_attr = element.get("d")
        if not d_attr:
            return []
        return list(parse_path_data(d_attr))

    if local_name == "line":
        x1 = float(element.get("x1", "0"))
        y1 = float(element.get("y1", "0"))
        x2 = float(element.get("x2", "0"))
        y2 = float(element.get("y2", "0"))
        return [LineSegment(Point(x1, y1), Point(x2, y2))]

    if local_name == "polyline" or local_name == "polygon":
        points_attr = element.get("points")
        if not points_attr:
            return []
        points = [
            Point(float(x), float(y))
            for chunk in points_attr.strip().split()
            for x, y in (chunk.split(","),)
        ]
        if local_name == "polygon" and points:
            points.append(points[0])
        segments: list[SegmentType] = []
        for start, end in zip(points[:-1], points[1:], strict=True):
            segments.append(LineSegment(start, end))
        return segments

    if local_name == "circle":
        cx = float(element.get("cx", "0"))
        cy = float(element.get("cy", "0"))
        r = float(element.get("r", "0"))
        if r <= 0:
            return []
        return _circle_segments(cx, cy, r)

    if local_name == "ellipse":
        cx = float(element.get("cx", "0"))
        cy = float(element.get("cy", "0"))
        rx = float(element.get("rx", "0"))
        ry = float(element.get("ry", "0"))
        if rx <= 0 or ry <= 0:
            return []
        return _ellipse_segments(cx, cy, rx, ry)

    if local_name == "rect":
        x = float(element.get("x", "0"))
        y = float(element.get("y", "0"))
        width = float(element.get("width", "0"))
        height = float(element.get("height", "0"))
        if width <= 0 or height <= 0:
            return []
        return [
            LineSegment(Point(x, y), Point(x + width, y)),
            LineSegment(Point(x + width, y), Point(x + width, y + height)),
            LineSegment(Point(x + width, y + height), Point(x, y + height)),
            LineSegment(Point(x, y + height), Point(x, y)),
        ]

    return []


def _circle_segments(cx: float, cy: float, r: float) -> list[SegmentType]:
    return _ellipse_segments(cx, cy, r, r)


def _ellipse_segments(cx: float, cy: float, rx: float, ry: float) -> list[SegmentType]:
    kappa = 0.5522847498307936
    control_x = rx * kappa
    control_y = ry * kappa
    points = [
        Point(cx, cy - ry),
        Point(cx + control_x, cy - ry),
        Point(cx + rx, cy - control_y),
        Point(cx + rx, cy),
        Point(cx + rx, cy + control_y),
        Point(cx + control_x, cy + ry),
        Point(cx, cy + ry),
        Point(cx - control_x, cy + ry),
        Point(cx - rx, cy + control_y),
        Point(cx - rx, cy),
        Point(cx - rx, cy - control_y),
        Point(cx - control_x, cy - ry),
        Point(cx, cy - ry),
    ]
    segments: list[SegmentType] = []
    for idx in range(0, len(points) - 3, 3):
        segments.append(
            BezierSegment(
                start=points[idx],
                control1=points[idx + 1],
                control2=points[idx + 2],
                end=points[idx + 3],
            )
        )
    return segments


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
        angle = _segment_angle(segment, forward=True, tolerance=tolerance)
        return segment.start, angle
    if position == "end":
        segment = segments[-1]
        angle = _segment_angle(segment, forward=False, tolerance=tolerance)
        return segment.end, angle
    return None


def _compute_mid_markers(
    segments: list[SegmentType],
    *,
    tolerance: float,
) -> list[tuple[Point, float]]:
    anchors: list[tuple[Point, float]] = []
    if len(segments) < 2:
        return anchors
    for first, second in zip(segments[:-1], segments[1:], strict=True):
        join_point = first.end
        angle_in = _segment_angle(first, forward=False, tolerance=tolerance)
        angle_out = _segment_angle(second, forward=True, tolerance=tolerance)
        angle = (angle_in + angle_out) / 2.0
        anchors.append((join_point, angle))
    return anchors


def _segment_angle(segment: SegmentType, *, forward: bool, tolerance: float) -> float:
    points = _segment_points(segment)
    if len(points) < 2:
        return 0.0
    if forward:
        start, end = points[0], points[-1]
    else:
        start, end = points[-1], points[0]
    dx = end.x - start.x
    dy = end.y - start.y
    if abs(dx) < tolerance and abs(dy) < tolerance:
        return 0.0
    return math.degrees(math.atan2(dy, dx))


def _segment_points(segment: SegmentType) -> list[Point]:
    if isinstance(segment, LineSegment):
        return [segment.start, segment.end]
    if isinstance(segment, BezierSegment):
        return [segment.start, segment.control1, segment.control2, segment.end]
    return []


def _expand_marker_use(converter, element: etree._Element) -> list[etree._Element]:
    href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")
    ref_id = local_url_id(href)
    if ref_id is None:
        return []
    referenced = converter._element_index.get(ref_id)
    if referenced is None:
        return []
    return [converter._clone_element(referenced)]


__all__ = ["apply_marker_metadata", "build_marker_shapes"]
