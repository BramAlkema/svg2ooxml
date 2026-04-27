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
    MarkerInstance,
    apply_local_transform,
    build_marker_transform,
)
from svg2ooxml.ir.geometry import SegmentType
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


__all__ = ["apply_marker_metadata", "build_marker_shapes"]
