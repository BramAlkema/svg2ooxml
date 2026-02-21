"""Motion animation handler.

Generates PowerPoint ``<p:animMotion>`` elements with SVG-derived motion
paths for ``<animateMotion>`` animations.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import p_elem, p_sub
from svg2ooxml.ir.animation import AnimationType

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

        if len(points) < 2:
            return None

        # Convert points to normalised slide-fraction coordinates
        motion_path = self._build_motion_path_string(points)
        pts_types = "A" * len(points)
        rotation = self._resolve_rotation_angle(animation, points)

        # Build <p:animMotion>
        anim_motion = p_elem(
            "animMotion",
            origin="layout",
            path=motion_path,
            pathEditMode="relative",
            rAng=rotation,
            ptsTypes=pts_types,
        )

        # Behavior core
        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            attr_name_list=["ppt_x", "ppt_y"],
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        anim_motion.append(cBhvr)

        # Rotation center
        p_sub(anim_motion, "rCtr", x="4306", y="0")

        # Wrap in <p:par>
        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=anim_motion,
            preset_id=0,
            preset_class="path",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
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

    def _build_motion_path_string(
        self, points: list[tuple[float, float]]
    ) -> str:
        """Convert parsed points to a PowerPoint motion path string.

        Points are converted from pixel deltas (relative to the first point)
        into slide-fraction coordinates.
        """
        from svg2ooxml.drawingml.writer import DEFAULT_SLIDE_SIZE

        slide_w, slide_h = DEFAULT_SLIDE_SIZE
        start_x, start_y = points[0]

        segments: list[str] = []
        for i, (x_px, y_px) in enumerate(points):
            dx_px = x_px - start_x
            dy_px = y_px - start_y

            dx_emu = self._units.to_emu(dx_px, axis="x")
            dy_emu = self._units.to_emu(dy_px, axis="y")

            nx = dx_emu / slide_w
            ny = dy_emu / slide_h

            cmd = "M" if i == 0 else "L"
            segments.append(f"{cmd} {self._format_coord(nx)} {self._format_coord(ny)}")

        return " ".join(segments) + " "

    @staticmethod
    def _format_coord(value: float) -> str:
        """Format normalised coordinate as a string."""
        if abs(value) < 1e-10:
            return "0"
        return f"{value:.6g}"

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
