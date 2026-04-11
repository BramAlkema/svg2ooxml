"""Motion animation handler.

Generates PowerPoint ``<p:animMotion>`` elements with SVG-derived motion
paths for ``<animateMotion>`` animations.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import p_elem, p_sub
from svg2ooxml.ir.animation import AnimationType, CalcMode

from ..timing_utils import compute_paced_key_times_2d

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
        points = self._retime_motion_points(points, animation)

        if len(points) < 2:
            return None

        # Convert points to normalised slide-fraction coordinates.
        # PowerPoint-authored motion paths terminate with "E" and do not
        # include the synthetic rCtr child we used in the early prototype.
        motion_path = self._build_motion_path_string(points)
        rotation = self._resolve_rotation_angle(animation, points)

        # Build <p:animMotion>
        anim_motion_attrs = {
            "origin": "layout",
            "path": motion_path,
            "pathEditMode": "relative",
        }
        if rotation != "0":
            anim_motion_attrs["rAng"] = rotation
        anim_motion = p_elem("animMotion", **anim_motion_attrs)

        # Behavior core
        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        anim_motion.append(cBhvr)

        # Wrap in <p:par>
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

    def _resolve_rotation_angle(
        self,
        animation: AnimationDefinition,
        points: list[tuple[float, float]],
    ) -> str:
        """Resolve animMotion rAng using motion rotate hints.

        PowerPoint does not support full SVG rotate="auto" semantics on path
        animations, so we approximate with a single tangent-derived angle.
        """
        rotate_mode = (animation.motion_rotate or "").strip().lower()
        if not rotate_mode:
            return "0"

        angle_deg: float | None = None
        if rotate_mode in {"auto", "auto-reverse"}:
            angle_deg = self._estimate_path_tangent_angle(points)
            if angle_deg is None:
                return "0"
            if rotate_mode == "auto-reverse":
                angle_deg += 180.0
        else:
            try:
                angle_deg = self._processor.parse_angle(rotate_mode)
            except (TypeError, ValueError):
                return "0"

        return self._processor.format_ppt_angle(angle_deg)

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

    # ------------------------------------------------------------------ #
    # Motion path helpers                                                 #
    # ------------------------------------------------------------------ #

    def _build_motion_path_string(self, points: list[tuple[float, float]]) -> str:
        """Convert parsed points to a PowerPoint motion path string.

        ``animateMotion`` paths in PowerPoint use the SVG-style command case:
        uppercase commands are absolute slide coordinates and lowercase
        commands are relative offsets. SVG motion paths are defined in the
        document coordinate space, so we emit absolute slide-fraction
        coordinates here instead of zero-based deltas from the first point.
        """
        from svg2ooxml.drawingml.writer import DEFAULT_SLIDE_SIZE

        slide_w, slide_h = DEFAULT_SLIDE_SIZE

        segments: list[str] = []
        for i, (x_px, y_px) in enumerate(points):
            x_emu = self._units.to_emu(x_px, axis="x")
            y_emu = self._units.to_emu(y_px, axis="y")

            nx = x_emu / slide_w
            ny = y_emu / slide_h

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
        key_times = animation.key_times
        if len(points) < 2 or key_times is None or len(key_times) < 2:
            return points

        calc_mode_value = (
            animation.calc_mode.value
            if isinstance(animation.calc_mode, CalcMode)
            else str(animation.calc_mode).lower()
        )
        key_points = self._sample_points_at_progress(points, key_times)
        if len(key_points) < 2:
            return points

        if calc_mode_value == CalcMode.PACED.value:
            paced_times = compute_paced_key_times_2d(key_points)
            if paced_times is not None:
                key_times = paced_times

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
