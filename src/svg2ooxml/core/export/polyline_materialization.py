"""Stroked polyline materialization for animation export."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from svg2ooxml.core.export.animation_predicates import (
    _is_polyline_segment_fade_animation,
    _is_simple_motion_sampling_candidate,
    _is_simple_origin_rotate_animation,
    _parse_rotate_bounds,
)
from svg2ooxml.core.export.motion_geometry import (
    _lerp,
    _rotate_point,
    _sample_progress_values,
)
from svg2ooxml.core.export.motion_path_sampling import (
    _build_sampled_motion_replacement,
    _parse_sampled_motion_points,
    _sample_polyline_at_fractions,
)
from svg2ooxml.core.export.scene_index import _scene_element_ids
from svg2ooxml.core.ir.converter import IRScene
from svg2ooxml.ir.animation import AnimationDefinition, AnimationType


@dataclass(frozen=True)
class _PolylineSegments:
    parent_center: tuple[float, float]
    segment_ids: list[str]
    segment_centers: list[tuple[float, float]]


def _materialize_stroked_polyline_groups(
    scene: IRScene,
    animations: list[AnimationDefinition],
) -> list[AnimationDefinition]:
    """Decompose stroked open paths into independently animated line segments."""

    from dataclasses import replace as _replace

    from svg2ooxml.ir.geometry import LineSegment
    from svg2ooxml.ir.scene import Group
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Line

    stroke_target_ids = {
        animation.element_id
        for animation in animations
        if (
            animation.animation_type == AnimationType.ANIMATE
            and animation.transform_type is None
            and animation.target_attribute == "stroke-width"
            and isinstance(animation.element_id, str)
        )
    }
    if not stroke_target_ids:
        return animations

    segment_map: dict[str, _PolylineSegments] = {}
    animations_by_target: dict[str, list[AnimationDefinition]] = {}
    for animation in animations:
        if isinstance(animation.element_id, str):
            animations_by_target.setdefault(animation.element_id, []).append(animation)

    def _is_supported_polyline_animation(animation: AnimationDefinition) -> bool:
        if (
            animation.animation_type == AnimationType.ANIMATE
            and animation.transform_type is None
            and animation.target_attribute == "stroke-width"
        ):
            return True
        if _is_polyline_segment_fade_animation(animation):
            return True
        if _is_simple_origin_rotate_animation(animation):
            return True
        if _is_simple_motion_sampling_candidate(animation):
            return True
        return False

    def _rewrite(element: Any):
        if isinstance(element, Group):
            return _replace(
                element,
                children=[_rewrite(child) for child in element.children],
            )
        if not isinstance(element, IRPath):
            return element
        if (
            element.fill is not None
            or element.clip
            or element.mask
            or element.mask_instance
            or getattr(element, "effects", None)
            or abs(float(getattr(element, "opacity", 1.0)) - 1.0) > 1e-6
        ):
            return element
        line_segments = [
            segment for segment in element.segments if isinstance(segment, LineSegment)
        ]
        if len(line_segments) < 2 or len(line_segments) != len(element.segments):
            return element
        metadata = getattr(element, "metadata", None)
        if not isinstance(metadata, dict):
            return element
        element_ids = _scene_element_ids(element)
        target_ids = [element_id for element_id in element_ids if element_id in stroke_target_ids]
        if not target_ids:
            return element
        if any(
            not _is_supported_polyline_animation(animation)
            for element_id in element_ids
            for animation in animations_by_target.get(element_id, [])
        ):
            return element

        base_id = next(
            (element_id for element_id in element_ids if not element_id.startswith("anim-target-")),
            target_ids[0],
        )
        segment_ids: list[str] = []
        segment_centers: list[tuple[float, float]] = []
        segment_children: list[Any] = []
        for index, segment in enumerate(line_segments):
            segment_id = f"{base_id}__seg{index}"
            segment_ids.append(segment_id)
            segment_centers.append(
                (
                    (float(segment.start.x) + float(segment.end.x)) / 2.0,
                    (float(segment.start.y) + float(segment.end.y)) / 2.0,
                )
            )
            child_metadata = dict(metadata)
            child_metadata["element_ids"] = [segment_id]
            segment_children.append(
                Line(
                    start=segment.start,
                    end=segment.end,
                    stroke=element.stroke,
                    opacity=1.0,
                    effects=[],
                    metadata=child_metadata,
                )
            )
        polyline_segments = _PolylineSegments(
            parent_center=(
                float(element.bbox.x + element.bbox.width / 2.0),
                float(element.bbox.y + element.bbox.height / 2.0),
            ),
            segment_ids=list(segment_ids),
            segment_centers=segment_centers,
        )
        for element_id in element_ids:
            segment_map[element_id] = polyline_segments

        return Group(children=segment_children)

    scene.elements = [_rewrite(element) for element in scene.elements]
    if not segment_map:
        return animations

    rewritten: list[AnimationDefinition] = []
    for animation in animations:
        segment_info = segment_map.get(animation.element_id)
        if segment_info is None:
            rewritten.append(animation)
            continue
        segment_ids = segment_info.segment_ids
        if (
            animation.animation_type == AnimationType.ANIMATE
            and animation.transform_type is None
            and animation.target_attribute == "stroke-width"
        ):
            rewritten.extend(
                _replace(animation, element_id=segment_id)
                for segment_id in segment_ids
            )
            continue
        if _is_polyline_segment_fade_animation(animation):
            rewritten.extend(
                _replace(animation, element_id=segment_id)
                for segment_id in segment_ids
            )
            continue
        if _is_simple_origin_rotate_animation(animation):
            rewritten.extend(
                _replace(animation, element_id=segment_id)
                for segment_id in segment_ids
            )
            continue
        if _is_simple_motion_sampling_candidate(animation):
            motion_points = _parse_sampled_motion_points(animation.values[0])
            if len(motion_points) < 2:
                rewritten.append(animation)
                continue
            rotate_member = next(
                (
                    candidate
                    for candidate in animations_by_target.get(animation.element_id, [])
                    if _is_simple_origin_rotate_animation(candidate)
                ),
                None,
            )
            if rotate_member is None:
                rewritten.extend(
                    _replace(animation, element_id=segment_id)
                    for segment_id in segment_ids
                )
                continue
            start_angle, end_angle = _parse_rotate_bounds(rotate_member)
            samples = _sample_progress_values()
            motion_samples = _sample_polyline_at_fractions(motion_points, samples)
            for segment_id, segment_center in zip(
                segment_ids,
                segment_info.segment_centers,
                strict=False,
            ):
                offset = (
                    segment_center[0] - segment_info.parent_center[0],
                    segment_center[1] - segment_info.parent_center[1],
                )
                child_center_points: list[tuple[float, float]] = []
                for progress, motion_point in zip(
                    samples,
                    motion_samples,
                    strict=True,
                ):
                    angle = _lerp(start_angle, end_angle, progress)
                    rotated_offset = _rotate_point(offset, angle)
                    child_center_points.append(
                        (
                            segment_info.parent_center[0]
                            + motion_point[0]
                            + rotated_offset[0],
                            segment_info.parent_center[1]
                            + motion_point[1]
                            + rotated_offset[1],
                        )
                    )
                rewritten.append(
                    _replace(
                        _build_sampled_motion_replacement(
                            template=animation,
                            points=child_center_points,
                        ),
                        element_id=segment_id,
                    )
                )
            continue
        rewritten.append(animation)
    return rewritten
