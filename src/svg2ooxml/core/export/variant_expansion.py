"""Multipage/variant expansion helpers, scene rewriting, and animation list transformations."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from svg2ooxml.core.export.animation_processor import (
    _is_polyline_segment_fade_animation,
    _is_simple_line_endpoint_animation,
    _is_simple_motion_sampling_candidate,
    _is_simple_origin_rotate_animation,
    _parse_rotate_bounds,
    _simple_position_axis,
    _timing_group_key,
)
from svg2ooxml.core.export.motion_geometry import (
    _build_sampled_motion_replacement,
    _format_motion_delta,
    _lerp,
    _parse_sampled_motion_points,
    _project_linear_motion_delta,
    _rotate_point,
    _sample_polyline_at_fraction,
    _sample_progress_values,
)
from svg2ooxml.core.ir.converter import IRScene
from svg2ooxml.ir.animation import (
    AnimationDefinition,
    AnimationType,
    CalcMode,
    TransformType,
)

# ---------------------------------------------------------------------------
# Trace report merging
# ---------------------------------------------------------------------------


def _merge_trace_reports(reports: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Merge multiple trace report dictionaries into a single aggregate report."""

    geometry_totals: Counter[str] = Counter()
    paint_totals: Counter[str] = Counter()
    stage_totals: Counter[str] = Counter()
    resvg_metrics: Counter[str] = Counter()
    geometry_events: list[Any] = []
    paint_events: list[Any] = []
    stage_events: list[Any] = []

    for report in reports:
        if not report:
            continue
        geometry_totals.update(report.get("geometry_totals", {}))
        paint_totals.update(report.get("paint_totals", {}))
        stage_totals.update(report.get("stage_totals", {}))
        resvg_metrics.update(report.get("resvg_metrics", {}))
        geometry_events.extend(report.get("geometry_events", []))
        paint_events.extend(report.get("paint_events", []))
        stage_events.extend(report.get("stage_events", []))

    return {
        "geometry_totals": dict(geometry_totals),
        "paint_totals": dict(paint_totals),
        "stage_totals": dict(stage_totals),
        "resvg_metrics": dict(resvg_metrics),
        "geometry_events": geometry_events,
        "paint_events": paint_events,
        "stage_events": stage_events,
    }


# ---------------------------------------------------------------------------
# Animation group key
# ---------------------------------------------------------------------------


def _animation_group_key(
    animation: AnimationDefinition,
    alias_map: dict[str, tuple[str, ...]],
) -> tuple[Any, ...]:
    return (
        alias_map.get(animation.element_id, (animation.element_id,)),
        *_timing_group_key(animation.timing),
        animation.additive,
        animation.accumulate,
        animation.calc_mode.value
        if isinstance(animation.calc_mode, CalcMode)
        else str(animation.calc_mode),
        animation.restart,
        animation.min_ms,
        animation.max_ms,
    )


# ---------------------------------------------------------------------------
# Simple line path materialization
# ---------------------------------------------------------------------------


def _materialize_simple_line_paths(
    scene: IRScene,
    animations: Sequence[AnimationDefinition],
) -> None:
    """Convert simple animated single-segment paths back into line IR."""

    from dataclasses import replace as _replace

    from svg2ooxml.ir.geometry import LineSegment
    from svg2ooxml.ir.scene import Group
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Line

    endpoint_target_ids = {
        animation.element_id
        for animation in animations
        if _is_simple_line_endpoint_animation(animation)
        and isinstance(animation.element_id, str)
    }
    if not endpoint_target_ids:
        return

    def _rewrite(element: Any):
        if isinstance(element, Group):
            return _replace(
                element,
                children=[_rewrite(child) for child in element.children],
            )
        if not isinstance(element, IRPath):
            return element
        if element.fill is not None or element.clip or element.mask or element.mask_instance:
            return element
        line_segments = [
            segment for segment in element.segments if isinstance(segment, LineSegment)
        ]
        if len(line_segments) != 1 or len(line_segments) != len(element.segments):
            return element
        metadata = getattr(element, "metadata", None)
        element_ids = metadata.get("element_ids", []) if isinstance(metadata, dict) else []
        if not any(
            isinstance(element_id, str) and element_id in endpoint_target_ids
            for element_id in element_ids
        ):
            return element
        segment = line_segments[0]
        return Line(
            start=segment.start,
            end=segment.end,
            stroke=element.stroke,
            opacity=element.opacity,
            effects=list(getattr(element, "effects", [])),
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )

    scene.elements = [_rewrite(element) for element in scene.elements]


# ---------------------------------------------------------------------------
# Stroked polyline group materialization
# ---------------------------------------------------------------------------


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

    @dataclass(frozen=True)
    class _PolylineSegments:
        parent_center: tuple[float, float]
        segment_ids: list[str]
        segment_centers: list[tuple[float, float]]

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
        element_ids = [
            element_id
            for element_id in metadata.get("element_ids", [])
            if isinstance(element_id, str)
        ]
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
                for progress in _sample_progress_values():
                    motion_point = _sample_polyline_at_fraction(motion_points, progress)
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


# ---------------------------------------------------------------------------
# Simple line endpoint animation composition
# ---------------------------------------------------------------------------


def _compose_simple_line_endpoint_animations(
    animations: list[AnimationDefinition],
    scene: IRScene,
) -> list[AnimationDefinition]:
    """Compose simple line endpoint changes into motion + scale fragments.

    Endpoint animations such as ``x1`` on a cloned line are geometry-local, not
    whole-shape translation. For simple line geometry, we can still approximate
    the authored SVG behavior by:

    1. translating the line center by the averaged endpoint delta
    2. scaling the line's local width/height around its center

    This prevents invalid native output such as treating ``x1`` and outer
    ``<use x>`` as duplicate full-shape motions.
    """
    from dataclasses import replace as _replace

    from svg2ooxml.ir.geometry import LineSegment
    from svg2ooxml.ir.scene import Group
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Line

    alias_map: dict[str, tuple[str, ...]] = {}
    line_points_map: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}

    def _resolve_line_points(
        element: object,
    ) -> tuple[tuple[float, float], tuple[float, float]] | None:
        if isinstance(element, Line):
            return (
                (float(element.start.x), float(element.start.y)),
                (float(element.end.x), float(element.end.y)),
            )

        if isinstance(element, IRPath):
            line_segments = [
                segment
                for segment in element.segments
                if isinstance(segment, LineSegment)
            ]
            if len(line_segments) != 1:
                return None
            segment = line_segments[0]
            return (
                (float(segment.start.x), float(segment.start.y)),
                (float(segment.end.x), float(segment.end.y)),
            )

        return None

    def _walk(elements: list) -> None:
        for el in elements:
            meta = getattr(el, "metadata", None)
            if isinstance(meta, dict):
                element_ids = tuple(
                    dict.fromkeys(
                        eid
                        for eid in meta.get("element_ids", [])
                        if isinstance(eid, str) and eid
                    )
                )
                if element_ids:
                    for element_id in element_ids:
                        alias_map[element_id] = element_ids
                    line_points = _resolve_line_points(el)
                    if line_points is not None:
                        for element_id in element_ids:
                            line_points_map[element_id] = line_points
            if isinstance(el, Group):
                _walk(getattr(el, "children", []))

    _walk(scene.elements)

    group_map: dict[tuple[Any, ...], list[tuple[int, str, AnimationDefinition]]] = {}
    for index, animation in enumerate(animations):
        if animation.animation_type != AnimationType.ANIMATE:
            continue
        if animation.transform_type is not None:
            continue
        attr = animation.target_attribute
        if attr in {"x1", "x2", "y1", "y2"}:
            if not _is_simple_line_endpoint_animation(animation):
                continue
        elif _simple_position_axis(animation) is None:
            continue
        group_key = _animation_group_key(animation, alias_map)
        group_map.setdefault(group_key, []).append((index, attr, animation))

    replacements: dict[int, tuple[list[AnimationDefinition], set[int]]] = {}
    for members in group_map.values():
        endpoint_members = [
            member for member in members if member[1] in {"x1", "x2", "y1", "y2"}
        ]
        if not endpoint_members:
            continue

        base_animation = min(members, key=lambda member: member[0])[2]
        line_points = line_points_map.get(base_animation.element_id)
        if line_points is None:
            continue

        attr_to_member: dict[str, tuple[int, AnimationDefinition]] = {}
        duplicate_attr = False
        for index, attr, animation in endpoint_members:
            if attr in attr_to_member:
                duplicate_attr = True
                break
            attr_to_member[attr] = (index, animation)
        if duplicate_attr:
            continue

        x_members = [member for member in members if _simple_position_axis(member[2]) == "x"]
        y_members = [member for member in members if _simple_position_axis(member[2]) == "y"]
        if len(x_members) > 1 or len(y_members) > 1:
            continue

        def _delta_for(
            attr_name: str,
            _members: dict[str, tuple[int, AnimationDefinition]] = attr_to_member,
        ) -> float:
            member = _members.get(attr_name)
            if member is None:
                return 0.0
            try:
                return float(member[1].values[-1]) - float(member[1].values[0])
            except (TypeError, ValueError):
                raise ValueError(attr_name) from None

        try:
            dx1 = _delta_for("x1")
            dx2 = _delta_for("x2")
            dy1 = _delta_for("y1")
            dy2 = _delta_for("y2")
        except ValueError:
            continue

        try:
            world_dx = (
                float(x_members[0][2].values[-1]) - float(x_members[0][2].values[0])
                if x_members
                else 0.0
            )
            world_dy = (
                float(y_members[0][2].values[-1]) - float(y_members[0][2].values[0])
                if y_members
                else 0.0
            )
        except (TypeError, ValueError):
            continue

        (x1_start, y1_start), (x2_start, y2_start) = line_points
        x1_end = x1_start + dx1
        y1_end = y1_start + dy1
        x2_end = x2_start + dx2
        y2_end = y2_start + dy2

        start_width = abs(x1_start - x2_start)
        start_height = abs(y1_start - y2_start)
        end_width = abs(x1_end - x2_end)
        end_height = abs(y1_end - y2_end)

        start_dx_sign = x1_start - x2_start
        end_dx_sign = x1_end - x2_end
        start_dy_sign = y1_start - y2_start
        end_dy_sign = y1_end - y2_end
        if (
            abs(start_dx_sign) > 1e-6
            and abs(end_dx_sign) > 1e-6
            and start_dx_sign * end_dx_sign < 0
        ) or (
            abs(start_dy_sign) > 1e-6
            and abs(end_dy_sign) > 1e-6
            and start_dy_sign * end_dy_sign < 0
        ):
            continue
        if (start_width <= 1e-6 and end_width > 1e-6) or (
            start_height <= 1e-6 and end_height > 1e-6
        ):
            continue

        scale_x = end_width / start_width if start_width > 1e-6 else 1.0
        scale_y = end_height / start_height if start_height > 1e-6 else 1.0

        local_dx = (dx1 + dx2) / 2.0
        local_dy = (dy1 + dy2) / 2.0
        total_dx = world_dx + local_dx
        total_dy = world_dy + local_dy
        matrix_source = (
            x_members[0][2]
            if x_members
            else (y_members[0][2] if y_members else base_animation)
        )
        total_dx, total_dy = _project_linear_motion_delta(
            total_dx,
            total_dy,
            matrix_source,
        )

        if (
            abs(total_dx) <= 1e-6
            and abs(total_dy) <= 1e-6
            and abs(scale_x - 1.0) <= 1e-6
            and abs(scale_y - 1.0) <= 1e-6
        ):
            continue

        consumed = {member[0] for member in endpoint_members}
        if x_members:
            consumed.add(x_members[0][0])
        if y_members:
            consumed.add(y_members[0][0])

        viewport = base_animation.motion_viewport_px
        if viewport is None and x_members:
            viewport = x_members[0][2].motion_viewport_px
        if viewport is None and y_members:
            viewport = y_members[0][2].motion_viewport_px

        replacement_group: list[AnimationDefinition] = []
        if abs(total_dx) > 1e-6 or abs(total_dy) > 1e-6:
            path = (
                f"M 0 0 L {_format_motion_delta(total_dx)} "
                f"{_format_motion_delta(total_dy)} E"
            )
            replacement_group.append(
                _replace(
                    base_animation,
                    animation_type=AnimationType.ANIMATE_MOTION,
                    target_attribute="position",
                    values=[path],
                    key_times=None,
                    key_splines=None,
                    calc_mode=CalcMode.LINEAR,
                    transform_type=None,
                    additive="replace",
                    accumulate="none",
                    motion_rotate=None,
                    element_motion_offset_px=None,
                    motion_space_matrix=None,
                    motion_viewport_px=viewport,
                )
            )

        if abs(scale_x - 1.0) > 1e-6 or abs(scale_y - 1.0) > 1e-6:
            replacement_group.append(
                _replace(
                    base_animation,
                    animation_type=AnimationType.ANIMATE_TRANSFORM,
                    target_attribute="transform",
                    values=["1 1", f"{scale_x:.6g} {scale_y:.6g}"],
                    key_times=None,
                    key_splines=None,
                    calc_mode=CalcMode.LINEAR,
                    transform_type=TransformType.SCALE,
                    additive="replace",
                    accumulate="none",
                    motion_rotate=None,
                    element_motion_offset_px=None,
                    motion_space_matrix=None,
                    motion_viewport_px=viewport,
                )
            )

        if not replacement_group:
            continue

        first_index = min(consumed)
        replacements[first_index] = (replacement_group, consumed)

    composed: list[AnimationDefinition] = []
    consumed: set[int] = set()
    for index, animation in enumerate(animations):
        if index in consumed:
            continue
        replacement = replacements.get(index)
        if replacement is not None:
            composed.extend(replacement[0])
            consumed.update(replacement[1])
            continue
        composed.append(animation)
    return composed


# ---------------------------------------------------------------------------
# Coalesce simple position motions
# ---------------------------------------------------------------------------


def _coalesce_simple_position_motions(
    animations: list[AnimationDefinition],
    scene: IRScene,
) -> list[AnimationDefinition]:
    """Merge simple x/y animations into one motion path per rendered shape.

    PowerPoint does not reliably compose concurrent one-axis ``animMotion``
    effects on the same target shape. When SVG expresses independent x/y
    animations that land on one rendered shape, collapse them into a single
    diagonal motion path before emitting timing XML.
    """
    from dataclasses import replace as _replace

    from svg2ooxml.ir.scene import Group

    alias_map: dict[str, tuple[str, ...]] = {}

    def _walk(elements: list) -> None:
        for el in elements:
            meta = getattr(el, "metadata", None)
            if isinstance(meta, dict):
                element_ids = tuple(
                    dict.fromkeys(
                        eid
                        for eid in meta.get("element_ids", [])
                        if isinstance(eid, str) and eid
                    )
                )
                if element_ids:
                    for element_id in element_ids:
                        alias_map[element_id] = element_ids
            if isinstance(el, Group):
                _walk(getattr(el, "children", []))

    _walk(scene.elements)

    group_map: dict[tuple[Any, ...], list[tuple[int, str, AnimationDefinition]]] = {}
    for index, animation in enumerate(animations):
        axis = _simple_position_axis(animation)
        if axis is None:
            continue

        group_key = _animation_group_key(animation, alias_map)
        group_map.setdefault(group_key, []).append((index, axis, animation))

    replacements: dict[int, tuple[AnimationDefinition, set[int]]] = {}
    for members in group_map.values():
        x_members = [member for member in members if member[1] == "x"]
        y_members = [member for member in members if member[1] == "y"]
        if len(x_members) != 1 or len(y_members) != 1:
            continue

        first_index = min(x_members[0][0], y_members[0][0])
        base_animation = animations[first_index]
        x_animation = x_members[0][2]
        y_animation = y_members[0][2]

        try:
            dx = float(x_animation.values[-1]) - float(x_animation.values[0])
            dy = float(y_animation.values[-1]) - float(y_animation.values[0])
        except (TypeError, ValueError):
            continue
        dx, dy = _project_linear_motion_delta(dx, dy, base_animation)

        path = (
            f"M 0 0 L {_format_motion_delta(dx)} "
            f"{_format_motion_delta(dy)} E"
        )
        replacement = _replace(
            base_animation,
            animation_type=AnimationType.ANIMATE_MOTION,
            target_attribute="position",
            values=[path],
            key_times=None,
            key_splines=None,
            calc_mode=CalcMode.LINEAR,
            transform_type=None,
            motion_rotate=None,
            element_motion_offset_px=None,
            motion_space_matrix=None,
            motion_viewport_px=(
                base_animation.motion_viewport_px
                or x_animation.motion_viewport_px
                or y_animation.motion_viewport_px
            ),
        )
        replacements[first_index] = (
            replacement,
            {x_members[0][0], y_members[0][0]},
        )

    coalesced: list[AnimationDefinition] = []
    consumed: set[int] = set()
    for index, animation in enumerate(animations):
        if index in consumed:
            continue
        replacement = replacements.get(index)
        if replacement is not None:
            coalesced.append(replacement[0])
            consumed.update(replacement[1])
            continue
        coalesced.append(animation)
    return coalesced
