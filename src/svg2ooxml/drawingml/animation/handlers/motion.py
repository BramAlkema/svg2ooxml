"""Motion animation handler.

Generates PowerPoint ``<p:animMotion>`` elements with SVG-derived motion
paths for ``<animateMotion>`` animations.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.animation.timing_utils import (
    compute_paced_key_times_2d,
    compute_segment_durations_ms,
)
from svg2ooxml.drawingml.xml_builder import p_elem
from svg2ooxml.ir.animation import AnimationType, CalcMode

from .base import AnimationHandler

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition

__all__ = ["MotionAnimationHandler"]


class MotionAnimationHandler(AnimationHandler):
    """Handler for motion path animations (``<animateMotion>``)."""

    def can_handle(self, animation: AnimationDefinition) -> bool:
        return animation.animation_type == AnimationType.ANIMATE_MOTION

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element | None:
        """Build ``<p:par>`` containing ``<p:animMotion>`` with path data."""
        if not animation.values:
            return None

        path_value = animation.values[0]
        points = self._parse_motion_path(path_value)
        points = self._project_motion_points(points, animation)
        points = self._retime_motion_points(points, animation)

        if len(points) < 2:
            return None

        motion_path = self._build_motion_path_string(points, animation)
        rotate_mode = self._resolve_rotate_mode(animation)
        if rotate_mode in {"auto", "auto-reverse"}:
            point_angles = self._sample_path_tangent_angles(points, rotate_mode)
            point_angles = self._apply_element_heading_offset(point_angles, animation)
            exact_initial_angle = self._resolve_exact_initial_tangent_angle(
                path_value,
                animation,
                rotate_mode,
            )
            if exact_initial_angle is not None and point_angles:
                point_angles[0] = exact_initial_angle
            if self._has_dynamic_rotation(point_angles):
                rotation_children = self._build_rotation_segment_children(
                    animation=animation,
                    base_behavior_id=behavior_id,
                    point_angles=point_angles,
                )
                if rotation_children:
                    anim_motion = self._build_anim_motion_element(
                        animation=animation,
                        behavior_id=behavior_id,
                        motion_path=motion_path,
                        rotation="0",
                        repeat_count=None,
                    )
                    child_elements: list[etree._Element] = [anim_motion, *rotation_children]
                    return self._xml.build_par_container_with_children_elem(
                        par_id=par_id,
                        duration_ms=animation.duration_ms,
                        delay_ms=animation.begin_ms,
                        child_elements=child_elements,
                        preset_id=0,
                        preset_class="path",
                        preset_subtype=0,
                        node_type="clickEffect",
                        begin_triggers=animation.begin_triggers,
                        default_target_shape=animation.element_id,
                        effect_group_id=par_id,
                        repeat_count=animation.repeat_count,
                    )

        rotation = self._resolve_rotation_angle(animation, points)
        anim_motion = self._build_anim_motion_element(
            animation=animation,
            behavior_id=behavior_id,
            motion_path=motion_path,
            rotation=rotation,
            repeat_count=animation.repeat_count,
        )
        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=anim_motion,
            preset_id=0,
            preset_class="path",
            preset_subtype=0,
            node_type="clickEffect",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
            effect_group_id=par_id,
        )

    def _build_anim_motion_element(
        self,
        *,
        animation: AnimationDefinition,
        behavior_id: int,
        motion_path: str,
        rotation: str,
        repeat_count: int | str | None,
    ) -> etree._Element:
        """Build the core ``<p:animMotion>`` element."""
        anim_motion_attrs = {
            "origin": "layout",
            "path": motion_path,
            "pathEditMode": "relative",
        }
        if rotation != "0":
            anim_motion_attrs["rAng"] = rotation

        anim_motion = p_elem("animMotion", **anim_motion_attrs)
        anim_motion.append(
            self._xml.build_behavior_core_elem(
                behavior_id=behavior_id,
                duration_ms=animation.duration_ms,
                target_shape=animation.element_id,
                additive=animation.additive,
                fill_mode=animation.fill_mode,
                repeat_count=repeat_count,
            )
        )
        return anim_motion

    @staticmethod
    def _resolve_rotate_mode(animation: AnimationDefinition) -> str:
        return (animation.motion_rotate or "").strip().lower()

    def _resolve_rotation_angle(
        self,
        animation: AnimationDefinition,
        points: list[tuple[float, float]],
    ) -> str:
        """Resolve animMotion rAng using motion rotate hints.

        PowerPoint does not support full SVG rotate="auto" semantics on path
        animations, so we approximate with a single tangent-derived angle.
        """
        rotate_mode = self._resolve_rotate_mode(animation)
        if not rotate_mode:
            return "0"

        angle_deg: float | None = None
        if rotate_mode in {"auto", "auto-reverse"}:
            point_angles = self._sample_path_tangent_angles(points, rotate_mode)
            if not point_angles:
                return "0"
            angle_deg = point_angles[0]
        else:
            try:
                angle_deg = self._processor.parse_angle(rotate_mode)
            except (TypeError, ValueError):
                return "0"

        heading = animation.element_heading_deg
        if heading is not None:
            angle_deg -= heading

        return self._processor.format_ppt_angle(angle_deg)

    def _resolve_exact_initial_tangent_angle(
        self,
        path_value: str,
        animation: AnimationDefinition,
        rotate_mode: str,
    ) -> float | None:
        """Resolve the exact tangent angle at the start of the SVG motion path."""
        vector = self._resolve_initial_tangent_vector(path_value)
        if vector is None:
            return None

        dx, dy = vector
        matrix = animation.motion_space_matrix
        if matrix is not None:
            a, b, c, d, _e, _f = matrix
            dx, dy = (a * dx + c * dy, b * dx + d * dy)

        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return None

        angle = math.degrees(math.atan2(dy, dx))
        if rotate_mode == "auto-reverse":
            angle += 180.0
        heading = animation.element_heading_deg
        if heading is not None:
            angle -= heading
        return angle

    @staticmethod
    def _apply_element_heading_offset(
        point_angles: list[float],
        animation: AnimationDefinition,
    ) -> list[float]:
        heading = animation.element_heading_deg
        if heading is None:
            return point_angles
        return [angle - heading for angle in point_angles]

    @staticmethod
    def _resolve_initial_tangent_vector(
        path_value: str,
    ) -> tuple[float, float] | None:
        """Return the first non-zero tangent vector from the SVG path data."""
        if not path_value:
            return None

        try:
            from svg2ooxml.common.geometry.paths import (
                PathParseError,
                parse_path_data,
            )
            from svg2ooxml.common.geometry.paths.segments import (
                BezierSegment,
                LineSegment,
            )
        except ImportError:
            return None

        try:
            segments = parse_path_data(path_value)
        except PathParseError:
            return None

        for segment in segments:
            if isinstance(segment, LineSegment):
                dx = segment.end.x - segment.start.x
                dy = segment.end.y - segment.start.y
                if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                    return (dx, dy)
                continue

            if isinstance(segment, BezierSegment):
                candidates = (
                    (
                        segment.control1.x - segment.start.x,
                        segment.control1.y - segment.start.y,
                    ),
                    (
                        segment.control2.x - segment.start.x,
                        segment.control2.y - segment.start.y,
                    ),
                    (
                        segment.end.x - segment.start.x,
                        segment.end.y - segment.start.y,
                    ),
                )
                for dx, dy in candidates:
                    if abs(dx) > 1e-9 or abs(dy) > 1e-9:
                        return (dx, dy)

        return None

    def _build_rotation_segment_children(
        self,
        *,
        animation: AnimationDefinition,
        base_behavior_id: int,
        point_angles: list[float],
    ) -> list[etree._Element]:
        """Build delayed ``animRot`` children to track the motion tangent."""
        if len(point_angles) < 2:
            return []

        child_elements: list[etree._Element] = []
        delay_acc = 0
        segment_index = 0
        initial_angle = point_angles[0]

        dynamic_deltas = [
            point_angles[angle_index + 1] - point_angles[angle_index]
            for angle_index in range(len(point_angles) - 1)
        ]
        has_dynamic_rotation = any(abs(delta) > 1e-6 for delta in dynamic_deltas)
        initial_duration = 1 if abs(initial_angle) > 1e-6 else 0

        if initial_duration:
            initial_behavior_id = base_behavior_id * 100 + 1
            initial_fill = animation.fill_mode if not has_dynamic_rotation else "hold"
            initial_rot = p_elem(
                "animRot",
                by=self._processor.format_ppt_angle(initial_angle),
            )
            initial_rot.append(
                self._xml.build_behavior_core_elem(
                    behavior_id=initial_behavior_id,
                    duration_ms=initial_duration,
                    target_shape=animation.element_id,
                    attr_name_list=["r"],
                    additive=animation.additive,
                    fill_mode=initial_fill,
                    repeat_count=None,
                )
            )
            child_elements.append(
                self._xml.build_delayed_child_par(
                    par_id=initial_behavior_id + 1,
                    delay_ms=0,
                    duration_ms=initial_duration,
                    child_element=initial_rot,
                )
            )
            delay_acc = initial_duration
            segment_index = 1

        dynamic_total_ms = max(1, animation.duration_ms - initial_duration)
        segment_durations = compute_segment_durations_ms(
            total_ms=dynamic_total_ms,
            n_values=len(point_angles),
        )

        for angle_index in range(len(point_angles) - 1):
            delta_deg = dynamic_deltas[angle_index]
            segment_duration = segment_durations[angle_index]
            if abs(delta_deg) <= 1e-6:
                delay_acc += segment_duration
                continue

            segment_behavior_id = base_behavior_id * 100 + segment_index * 2 + 1
            segment_par_id = segment_behavior_id + 1
            fill_mode = (
                animation.fill_mode
                if angle_index == len(point_angles) - 2
                else "hold"
            )
            anim_rot = p_elem(
                "animRot",
                by=self._processor.format_ppt_angle(delta_deg),
            )
            anim_rot.append(
                self._xml.build_behavior_core_elem(
                    behavior_id=segment_behavior_id,
                    duration_ms=segment_duration,
                    target_shape=animation.element_id,
                    attr_name_list=["r"],
                    additive=animation.additive,
                    fill_mode=fill_mode,
                    repeat_count=None,
                )
            )
            child_elements.append(
                self._xml.build_delayed_child_par(
                    par_id=segment_par_id,
                    delay_ms=delay_acc,
                    duration_ms=segment_duration,
                    child_element=anim_rot,
                )
            )
            delay_acc += segment_duration
            segment_index += 1

        return child_elements

    def _sample_path_tangent_angles(
        self,
        points: list[tuple[float, float]],
        rotate_mode: str,
    ) -> list[float]:
        """Return unwrapped tangent angles for each sampled motion point."""
        if len(points) < 2:
            return []

        segment_angles = [
            self._estimate_segment_tangent_angle(points[index], points[index + 1])
            for index in range(len(points) - 1)
        ]
        valid_angles = [angle for angle in segment_angles if angle is not None]
        if not valid_angles:
            return []

        fallback_angle = valid_angles[0]
        normalized_segments: list[float] = []
        for angle in segment_angles:
            resolved_angle = fallback_angle if angle is None else angle
            fallback_angle = resolved_angle
            normalized_segments.append(resolved_angle)

        point_angles = [normalized_segments[0], *normalized_segments]
        if rotate_mode == "auto-reverse":
            point_angles = [angle + 180.0 for angle in point_angles]
        return self._unwrap_angles(point_angles)

    @staticmethod
    def _has_dynamic_rotation(point_angles: list[float]) -> bool:
        if len(point_angles) < 2:
            return False
        return any(
            abs(point_angles[index + 1] - point_angles[index]) > 1e-6
            for index in range(len(point_angles) - 1)
        )

    @staticmethod
    def _estimate_path_tangent_angle(points: list[tuple[float, float]]) -> float | None:
        """Estimate tangent angle from the last non-zero path segment."""
        if len(points) < 2:
            return None

        for idx in range(len(points) - 1, 0, -1):
            x0, y0 = points[idx - 1]
            x1, y1 = points[idx]
            dx = x1 - x0
            dy = y1 - y0
            if abs(dx) < 1e-9 and abs(dy) < 1e-9:
                continue
            return math.degrees(math.atan2(dy, dx))

        return None

    @staticmethod
    def _estimate_segment_tangent_angle(
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> float | None:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return None
        return math.degrees(math.atan2(dy, dx))

    @staticmethod
    def _unwrap_angles(angles: list[float]) -> list[float]:
        """Unwrap angle samples so consecutive deltas stay continuous."""
        if not angles:
            return []

        unwrapped = [angles[0]]
        for angle in angles[1:]:
            adjusted = angle
            while adjusted - unwrapped[-1] > 180.0:
                adjusted -= 360.0
            while adjusted - unwrapped[-1] < -180.0:
                adjusted += 360.0
            unwrapped.append(adjusted)
        return unwrapped

    # ------------------------------------------------------------------ #
    # Motion path helpers                                                 #
    # ------------------------------------------------------------------ #

    def _project_motion_points(
        self,
        points: list[tuple[float, float]],
        animation: AnimationDefinition,
    ) -> list[tuple[float, float]]:
        """Project SVG motion points into absolute slide-space shape positions."""
        if not points:
            return points

        matrix = animation.motion_space_matrix
        if matrix is None:
            transformed = list(points)
        else:
            a, b, c, d, e, f = matrix
            transformed = [
                (a * x + c * y + e, b * x + d * y + f)
                for x, y in points
            ]

        offset_x = 0.0
        offset_y = 0.0
        if animation.element_motion_offset_px is not None:
            offset_x, offset_y = animation.element_motion_offset_px

        if abs(offset_x) < 1e-9 and abs(offset_y) < 1e-9:
            return transformed

        return [
            (x + offset_x, y + offset_y)
            for x, y in transformed
        ]

    def _build_motion_path_string(
        self,
        points: list[tuple[float, float]],
        animation: AnimationDefinition,
    ) -> str:
        """Convert parsed points to a PowerPoint motion path string.

        By the time this method is called, *points* contain absolute
        slide-space positions. PowerPoint motion effects expect the path to
        be expressed from the shape's starting position, so we subtract the
        first point before converting to slide fractions.
        """
        viewport_w = 960.0
        viewport_h = 720.0
        if animation.motion_viewport_px is not None:
            viewport_w = max(animation.motion_viewport_px[0], 1.0)
            viewport_h = max(animation.motion_viewport_px[1], 1.0)
        start_x, start_y = points[0]

        segments: list[str] = []
        for i, (x_px, y_px) in enumerate(points):
            dx_px = x_px - start_x
            dy_px = y_px - start_y

            nx = dx_px / viewport_w
            ny = dy_px / viewport_h

            cmd = "M" if i == 0 else "L"
            segments.append(f"{cmd} {self._format_coord(nx)} {self._format_coord(ny)}")

        return " ".join(segments) + " E"

    @staticmethod
    def _format_coord(value: float) -> str:
        """Format normalised coordinate as a string."""
        if abs(value) < 1e-10:
            return "0"
        return f"{value:.6g}"

    def _retime_motion_points(
        self,
        points: list[tuple[float, float]],
        animation: AnimationDefinition,
        segment_budget: int = 96,
    ) -> list[tuple[float, float]]:
        """Approximate keyTimes/calcMode timing by expanding path vertices."""
        if len(points) < 2:
            return points

        calc_mode_value = (
            animation.calc_mode.value
            if isinstance(animation.calc_mode, CalcMode)
            else str(animation.calc_mode).lower()
        )

        if animation.key_points is not None and len(animation.key_points) >= 2:
            key_points = self._sample_points_at_progress(points, animation.key_points)
            if (
                animation.key_times is not None
                and len(animation.key_times) == len(animation.key_points)
            ):
                key_times = list(animation.key_times)
            else:
                key_times = self._uniform_key_times(len(key_points))
        elif calc_mode_value == CalcMode.PACED.value:
            if len(points) < 3 and not animation.key_times:
                return points
            key_points = list(points)
            paced_times = compute_paced_key_times_2d(key_points)
            key_times = paced_times or self._uniform_key_times(len(key_points))
        elif animation.key_times is not None and len(animation.key_times) >= 2:
            key_times = list(animation.key_times)
            key_points = (
                list(points)
                if len(key_times) == len(points)
                else self._sample_points_at_progress(points, key_times)
            )
        elif calc_mode_value in {
            CalcMode.LINEAR.value,
            CalcMode.DISCRETE.value,
        } and len(points) > 2:
            key_points = list(points)
            key_times = self._uniform_key_times(len(key_points))
        else:
            return points

        if len(key_points) < 2 or len(key_times) != len(key_points):
            return points

        if calc_mode_value == CalcMode.DISCRETE.value:
            return self._expand_discrete_points(
                points=key_points,
                key_times=key_times,
                segment_budget=segment_budget,
            )

        return self._retime_linear_points(
            points=key_points,
            key_times=key_times,
            segment_budget=segment_budget,
        )

    @staticmethod
    def _uniform_key_times(count: int) -> list[float]:
        if count <= 1:
            return [0.0]
        return [index / (count - 1) for index in range(count)]

    @staticmethod
    def _sample_points_at_progress(
        points: list[tuple[float, float]],
        key_times: list[float],
    ) -> list[tuple[float, float]]:
        if len(points) < 2 or len(key_times) < 2:
            return points

        lengths = [0.0]
        total = 0.0
        for idx in range(1, len(points)):
            x0, y0 = points[idx - 1]
            x1, y1 = points[idx]
            total += math.hypot(x1 - x0, y1 - y0)
            lengths.append(total)

        if total <= 1e-9:
            return [points[0] for _ in key_times]

        sampled: list[tuple[float, float]] = []
        for fraction in key_times:
            target = max(0.0, min(1.0, fraction)) * total
            sampled.append(
                MotionAnimationHandler._sample_polyline_at_distance(
                    points=points,
                    cumulative_lengths=lengths,
                    target_distance=target,
                )
            )
        return sampled

    @staticmethod
    def _sample_polyline_at_distance(
        *,
        points: list[tuple[float, float]],
        cumulative_lengths: list[float],
        target_distance: float,
    ) -> tuple[float, float]:
        if target_distance <= 0.0:
            return points[0]
        if target_distance >= cumulative_lengths[-1]:
            return points[-1]

        for idx in range(1, len(points)):
            prev_dist = cumulative_lengths[idx - 1]
            curr_dist = cumulative_lengths[idx]
            if target_distance <= curr_dist:
                span = curr_dist - prev_dist
                if span <= 1e-9:
                    return points[idx]
                t = (target_distance - prev_dist) / span
                x0, y0 = points[idx - 1]
                x1, y1 = points[idx]
                return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)

        return points[-1]

    @staticmethod
    def _retime_linear_points(
        *,
        points: list[tuple[float, float]],
        key_times: list[float],
        segment_budget: int,
    ) -> list[tuple[float, float]]:
        expanded: list[tuple[float, float]] = [points[0]]
        for index in range(1, len(points)):
            start = points[index - 1]
            end = points[index]
            duration = max(0.0, key_times[index] - key_times[index - 1])
            segment_count = max(1, int(round(duration * segment_budget)))

            for step in range(1, segment_count + 1):
                t = step / segment_count
                x = start[0] + (end[0] - start[0]) * t
                y = start[1] + (end[1] - start[1]) * t
                expanded.append((x, y))

        return expanded

    @staticmethod
    def _expand_discrete_points(
        *,
        points: list[tuple[float, float]],
        key_times: list[float],
        segment_budget: int,
    ) -> list[tuple[float, float]]:
        expanded: list[tuple[float, float]] = [points[0]]
        for index in range(1, len(points)):
            prev = points[index - 1]
            curr = points[index]
            duration = max(0.0, key_times[index] - key_times[index - 1])
            slot_count = max(1, int(round(duration * segment_budget)))

            for _ in range(max(0, slot_count - 1)):
                expanded.append(prev)
            expanded.append(curr)

        return expanded

    # ------------------------------------------------------------------ #
    # Path parsing                                                        #
    # ------------------------------------------------------------------ #

    def _parse_motion_path(self, path_value: str) -> list[tuple[float, float]]:
        """Parse SVG motion path into list of (x, y) pixel tuples."""
        if not path_value:
            return []

        try:
            from svg2ooxml.common.geometry.paths import (
                PathParseError,
                parse_path_data,
            )
            from svg2ooxml.common.geometry.paths.segments import (
                BezierSegment,
                LineSegment,
            )
            from svg2ooxml.ir.geometry import Point
        except ImportError:
            return self._simple_path_parse(path_value)

        try:
            segments = parse_path_data(path_value)
        except PathParseError:
            return []

        if not segments:
            return []

        points: list[Point] = []
        points.append(segments[0].start)

        for segment in segments:
            if isinstance(segment, LineSegment):
                points.append(segment.end)
            elif isinstance(segment, BezierSegment):
                points.extend(self._sample_bezier(segment))

        return self._dedupe_points(points)

    def _sample_bezier(self, segment, *, steps: int = 20):
        """Sample a cubic bezier curve into *steps* evenly-spaced points."""

        samples = []
        for index in range(1, steps + 1):
            t = index / steps
            samples.append(self._bezier_point(segment, t))
        return samples

    def _bezier_point(self, segment, t: float):
        """De Casteljau evaluation of a cubic bezier at parameter *t*."""
        from svg2ooxml.ir.geometry import Point

        mt = 1.0 - t
        x = (
            mt**3 * segment.start.x
            + 3 * mt**2 * t * segment.control1.x
            + 3 * mt * t**2 * segment.control2.x
            + t**3 * segment.end.x
        )
        y = (
            mt**3 * segment.start.y
            + 3 * mt**2 * t * segment.control1.y
            + 3 * mt * t**2 * segment.control2.y
            + t**3 * segment.end.y
        )
        return Point(x=x, y=y)

    def _dedupe_points(self, points) -> list[tuple[float, float]]:
        """Remove consecutive duplicate points."""
        deduped: list[tuple[float, float]] = []
        epsilon = 1e-6

        for point in points:
            pair = (point.x, point.y)
            if not deduped or (
                abs(deduped[-1][0] - pair[0]) > epsilon
                or abs(deduped[-1][1] - pair[1]) > epsilon
            ):
                deduped.append(pair)

        return deduped

    def _simple_path_parse(self, path_value: str) -> list[tuple[float, float]]:
        """Fallback parser for basic M/L commands."""
        points: list[tuple[float, float]] = []
        tokens = path_value.replace(",", " ").split()

        i = 0
        while i < len(tokens):
            cmd = tokens[i]
            if cmd.upper() in ("M", "L"):
                if i + 2 < len(tokens):
                    try:
                        x = float(tokens[i + 1])
                        y = float(tokens[i + 2])
                        points.append((x, y))
                        i += 3
                    except ValueError:
                        i += 1
                else:
                    i += 1
            else:
                i += 1

        return points
