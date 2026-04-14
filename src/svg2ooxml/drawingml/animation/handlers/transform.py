"""Transform animation handler.

Generates PowerPoint ``<p:animScale>``, ``<p:animRot>``, or ``<p:animMotion>``
elements for ``<animateTransform>`` animations (scale, rotate, translate, matrix).
"""

from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.common.conversions.scale import scale_to_ppt
from svg2ooxml.common.units import emu_to_px
from svg2ooxml.drawingml.animation.timing_utils import (
    compute_paced_key_times_2d,
    compute_segment_durations_ms,
)
from svg2ooxml.drawingml.xml_builder import p_elem, p_sub
from svg2ooxml.ir.animation import CalcMode, TransformType

from .base import AnimationHandler

if TYPE_CHECKING:
    from svg2ooxml.common.geometry.matrix import Matrix2D
    from svg2ooxml.ir.animation import AnimationDefinition

__all__ = ["TransformAnimationHandler"]

_logger = logging.getLogger(__name__)


class TransformAnimationHandler(AnimationHandler):
    """Handler for transform animations (scale, rotate, translate, matrix)."""

    _SUPPORTED_TRANSFORMS = {
        TransformType.SCALE,
        TransformType.ROTATE,
        TransformType.TRANSLATE,
        TransformType.MATRIX,
    }

    def can_handle(self, animation: AnimationDefinition) -> bool:
        if animation.transform_type is None:
            return False
        return animation.transform_type in self._SUPPORTED_TRANSFORMS

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element | None:
        """Build ``<p:par>`` wrapping the appropriate transform animation element."""
        transform_type = animation.transform_type
        if transform_type is None:
            return None

        preset_class: str | None = None
        preset_id: int | None = None

        if transform_type == TransformType.SCALE:
            scale_pairs = [
                self._processor.parse_scale_pair(v) for v in animation.values
            ]
            child = self._build_scale_element(animation, behavior_id, scale_pairs)
            if child is None:
                return None
            scale_motion = self._build_scale_origin_motion(
                animation,
                behavior_id + 2,
                scale_pairs,
            )
            if scale_motion is not None:
                return self._xml.build_par_container_with_children_elem(
                    par_id=par_id,
                    duration_ms=animation.duration_ms,
                    delay_ms=animation.begin_ms,
                    child_elements=[child, scale_motion],
                    preset_id=6,
                    preset_class="emph",
                    preset_subtype=0,
                    node_type="clickEffect",
                    begin_triggers=animation.begin_triggers,
                    default_target_shape=animation.element_id,
                    effect_group_id=par_id,
                )
            preset_class = "emph"
            preset_id = 6  # Grow/Shrink
        elif transform_type == TransformType.ROTATE:
            parsed = [self._parse_rotate_value(v) for v in animation.values]
            angles = [p[0] for p in parsed]
            rotation_center = self._extract_rotation_center(parsed)

            if len(angles) > 2:
                return self._build_multi_keyframe_rotate(
                    animation,
                    par_id,
                    behavior_id,
                    angles,
                    rotation_center=rotation_center,
                )

            # Check if we need a companion orbital motion path
            orbit_offset = self._compute_orbit_offset(
                rotation_center,
                animation.element_center_px,
            )
            if orbit_offset is not None:
                return self._build_rotate_with_orbit(
                    animation,
                    par_id,
                    behavior_id,
                    angles,
                    orbit_offset,
                )

            child = self._build_rotate_element(animation, behavior_id, angles)
            preset_class = "emph"
            preset_id = 8  # Spin
        elif transform_type == TransformType.TRANSLATE:
            translation_pairs = [
                self._processor.parse_translation_pair(v) for v in animation.values
            ]
            child = self._build_translate_element(
                animation, behavior_id, translation_pairs
            )
            preset_class = "path"
            preset_id = 0  # Custom Path
        elif transform_type == TransformType.MATRIX:
            child, preset_class = self._build_matrix_element(animation, behavior_id)
        else:
            return None

        if child is None:
            return None

        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=child,
            preset_id=preset_id,
            preset_class=preset_class,
            preset_subtype=0 if preset_id else None,
            node_type="clickEffect",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
            effect_group_id=par_id,
        )

    # ------------------------------------------------------------------ #
    # Scale                                                                #
    # ------------------------------------------------------------------ #

    def _build_scale_element(
        self,
        animation: AnimationDefinition,
        behavior_id: int,
        scale_pairs: list[tuple[float, float]],
    ) -> etree._Element | None:
        if not scale_pairs:
            return None

        from_sx, from_sy = scale_pairs[0]
        to_sx, to_sy = scale_pairs[-1]

        anim_scale = p_elem("animScale")

        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        anim_scale.append(cBhvr)

        p_sub(
            anim_scale,
            "from",
            x=str(scale_to_ppt(from_sx)),
            y=str(scale_to_ppt(from_sy)),
        )
        p_sub(
            anim_scale,
            "to",
            x=str(scale_to_ppt(to_sx)),
            y=str(scale_to_ppt(to_sy)),
        )

        return anim_scale

    def _build_scale_origin_motion(
        self,
        animation: AnimationDefinition,
        behavior_id: int,
        scale_pairs: list[tuple[float, float]],
    ) -> etree._Element | None:
        """Compensate for SVG scaling around the origin.

        PowerPoint animScale grows around the shape center. SVG scale transforms
        grow around the current user-space origin, so the final SVG center is
        offset by ``center * (scale - 1)`` from the unanimated rendered center.
        Emit a companion motion path when we know that center.
        """
        if len(scale_pairs) < 2:
            return None
        if animation.element_center_px is None:
            return None

        to_sx, to_sy = scale_pairs[-1]
        center_x, center_y = animation.element_center_px
        delta_x = center_x * (to_sx - 1.0)
        delta_y = center_y * (to_sy - 1.0)
        if abs(delta_x) <= 1e-6 and abs(delta_y) <= 1e-6:
            return None

        viewport_w, viewport_h = self._resolve_motion_viewport_px(animation)
        path = (
            f"M 0 0 L {self._format_coord(delta_x / viewport_w)} "
            f"{self._format_coord(delta_y / viewport_h)} E"
        )

        anim_motion = p_elem(
            "animMotion",
            origin="layout",
            path=path,
            pathEditMode="relative",
            rAng="0",
            ptsTypes="AA",
        )
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
        p_sub(anim_motion, "rCtr", x="0", y="0")
        return anim_motion

    # ------------------------------------------------------------------ #
    # Rotate helpers                                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_rotate_value(value: str) -> tuple[float, float | None, float | None]:
        """Parse ``"angle [cx cy]"`` → ``(angle, cx, cy)``."""
        from svg2ooxml.common.conversions.transforms import parse_numeric_list

        nums = parse_numeric_list(value)
        if len(nums) >= 3:
            return (nums[0], nums[1], nums[2])
        if nums:
            return (nums[0], None, None)
        return (0.0, None, None)

    @staticmethod
    def _extract_rotation_center(
        parsed: list[tuple[float, float | None, float | None]],
    ) -> tuple[float, float] | None:
        """Return consistent (cx, cy) if all values share the same center."""
        cx, cy = None, None
        for _, vcx, vcy in parsed:
            if vcx is not None and vcy is not None:
                if cx is None:
                    cx, cy = vcx, vcy
                elif abs(vcx - cx) > 1e-6 or abs(vcy - cy) > 1e-6:
                    # Varying centers across keyframes — use first
                    return (cx, cy)
        if cx is not None and cy is not None:
            return (cx, cy)
        return None

    @staticmethod
    def _compute_orbit_offset(
        rotation_center: tuple[float, float] | None,
        element_center_px: tuple[float, float] | None,
    ) -> tuple[float, float] | None:
        """Return (dx, dy) offset from rotation center to shape center, or None."""
        if rotation_center is None or element_center_px is None:
            return None
        cx, cy = rotation_center
        sx, sy = element_center_px
        dx, dy = sx - cx, sy - cy
        # Skip if shape center ≈ rotation center (no orbit needed)
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            return None
        return (dx, dy)

    # ------------------------------------------------------------------ #
    # Rotate                                                               #
    # ------------------------------------------------------------------ #

    def _build_rotate_element(
        self,
        animation: AnimationDefinition,
        behavior_id: int,
        angles: list[float],
    ) -> etree._Element | None:
        if not angles:
            return None

        start_angle = angles[0]
        rotation_delta = self._processor.format_ppt_angle(angles[-1] - start_angle)

        anim_rot = p_elem("animRot", by=rotation_delta)

        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            attr_name_list=["r"],
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        anim_rot.append(cBhvr)

        return anim_rot

    def _build_rotate_with_orbit(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        angles: list[float],
        orbit_offset: tuple[float, float],
    ) -> etree._Element:
        """Build ``<p:par>`` with spin + orbital motion playing simultaneously."""
        delta_deg = angles[-1] - angles[0]
        rotation_delta = self._processor.format_ppt_angle(delta_deg)

        anim_rot = p_elem("animRot", by=rotation_delta)
        anim_rot.append(
            self._xml.build_behavior_core_elem(
                behavior_id=behavior_id,
                duration_ms=animation.duration_ms,
                target_shape=animation.element_id,
                attr_name_list=["r"],
                additive=animation.additive,
                fill_mode=animation.fill_mode,
                repeat_count=animation.repeat_count,
            )
        )

        anim_motion = self._build_orbital_motion_element(
            animation,
            behavior_id + 2,
            angles,
            orbit_offset,
        )
        child_elements = [anim_rot]
        if anim_motion is not None:
            child_elements.append(anim_motion)
        return self._xml.build_par_container_with_children_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_elements=child_elements,
            preset_id=8,
            preset_class="emph",
            preset_subtype=0,
            node_type="clickEffect",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
            effect_group_id=par_id,
            repeat_count=animation.repeat_count,
        )

    def _build_orbital_motion_element(
        self,
        animation: AnimationDefinition,
        behavior_id: int,
        angles: list[float],
        orbit_offset: tuple[float, float],
    ) -> etree._Element | None:
        """Build ``<p:animMotion>`` for the circular orbit around a rotation center.

        *orbit_offset* is (dx, dy) from rotation center to shape center in px.
        *angles* are the full keyframe angle sequence (may be 2+ values).
        """
        from svg2ooxml.drawingml.writer import DEFAULT_SLIDE_SIZE

        slide_w, slide_h = DEFAULT_SLIDE_SIZE
        dx_px, dy_px = orbit_offset
        start_deg = angles[0]
        total_sweep = angles[-1] - start_deg

        # Build arc path with line segments
        n_steps = max(8, int(abs(total_sweep) / 45.0) * 2)
        if n_steps < 2:
            return None

        segments: list[str] = ["M 0 0"]
        for step in range(1, n_steps + 1):
            # For multi-keyframe, interpolate through all angles
            t = step / n_steps
            # Linear interpolation through the full angle sequence
            if (
                len(angles) > 2
                and animation.key_times
                and len(animation.key_times) == len(angles)
            ):
                theta_deg = self._interpolate_angles(angles, animation.key_times, t)
            else:
                theta_deg = start_deg + total_sweep * t
            theta_rad = math.radians(theta_deg) - math.radians(start_deg)
            cos_t, sin_t = math.cos(theta_rad), math.sin(theta_rad)
            mx_px = dx_px * (cos_t - 1) - dy_px * sin_t
            my_px = dx_px * sin_t + dy_px * (cos_t - 1)
            mx_emu = self._units.to_emu(mx_px, axis="x")
            my_emu = self._units.to_emu(my_px, axis="y")
            segments.append(
                f"L {self._format_coord(mx_emu / slide_w)} {self._format_coord(my_emu / slide_h)}"
            )

        path = " ".join(segments) + " E"
        pts_types = "A" * (n_steps + 1)

        anim_motion = p_elem(
            "animMotion",
            origin="layout",
            path=path,
            pathEditMode="relative",
            rAng="0",
            ptsTypes=pts_types,
        )
        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        anim_motion.append(cBhvr)
        p_sub(anim_motion, "rCtr", x="0", y="0")
        return anim_motion

    @staticmethod
    def _interpolate_angles(
        angles: list[float],
        key_times: list[float],
        t: float,
    ) -> float:
        """Linearly interpolate through keyframed angles at normalised time *t*."""
        if t <= 0.0:
            return angles[0]
        if t >= 1.0:
            return angles[-1]
        for i in range(len(key_times) - 1):
            if t <= key_times[i + 1]:
                seg_t = (t - key_times[i]) / max(1e-9, key_times[i + 1] - key_times[i])
                return angles[i] + (angles[i + 1] - angles[i]) * seg_t
        return angles[-1]

    def _build_multi_keyframe_rotate(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        angles: list[float],
        *,
        rotation_center: tuple[float, float] | None = None,
    ) -> etree._Element:
        """Build a ``<p:par>`` with sequenced ``<p:animRot>`` segments.

        Splits N angles into N-1 segments so that multi-keyframe rotations
        like ``0 → 360 → 0`` produce two visible rotation steps instead of
        collapsing to ``by="0"``.
        """
        n_segments = len(angles) - 1
        total_ms = animation.duration_ms

        seg_durations = compute_segment_durations_ms(
            total_ms=total_ms,
            n_values=len(angles),
            key_times=(
                animation.key_times
                if animation.key_times and len(animation.key_times) == len(angles)
                else None
            ),
        )

        child_elements: list[etree._Element] = []
        bid = behavior_id
        delay_acc = 0

        for i in range(n_segments):
            delta_deg = angles[i + 1] - angles[i]
            rotation_delta = self._processor.format_ppt_angle(delta_deg)
            seg_dur = seg_durations[i]

            anim_rot = p_elem("animRot", by=rotation_delta)
            seg_fill = animation.fill_mode if i == n_segments - 1 else "hold"
            cBhvr = self._xml.build_behavior_core_elem(
                behavior_id=bid,
                duration_ms=seg_dur,
                target_shape=animation.element_id,
                attr_name_list=["r"],
                additive=animation.additive,
                fill_mode=seg_fill,
                repeat_count=None,
            )
            anim_rot.append(cBhvr)

            child_elements.append(
                self._xml.build_delayed_child_par(
                    par_id=bid + 1,
                    delay_ms=delay_acc,
                    duration_ms=seg_dur,
                    child_element=anim_rot,
                )
            )
            delay_acc += seg_dur
            bid += 2

        # Add orbital motion if rotation center ≠ shape center
        orbit_offset = self._compute_orbit_offset(
            rotation_center,
            animation.element_center_px,
        )
        if orbit_offset is not None:
            orbit_motion = self._build_orbital_motion_element(
                animation,
                bid,
                angles,
                orbit_offset,
            )
            if orbit_motion is not None:
                child_elements.append(
                    self._xml.build_delayed_child_par(
                        par_id=bid + 1,
                        delay_ms=0,
                        duration_ms=total_ms,
                        child_element=orbit_motion,
                    )
                )

        return self._xml.build_par_container_with_children_elem(
            par_id=par_id,
            duration_ms=total_ms,
            delay_ms=animation.begin_ms,
            child_elements=child_elements,
            preset_id=8,
            preset_class="emph",
            preset_subtype=0,
            node_type="clickEffect",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
            effect_group_id=par_id,
            repeat_count=animation.repeat_count,
        )

    # ------------------------------------------------------------------ #
    # Translate                                                            #
    # ------------------------------------------------------------------ #

    def _build_translate_element(
        self,
        animation: AnimationDefinition,
        behavior_id: int,
        translation_pairs: list[tuple[float, float]],
    ) -> etree._Element | None:
        if len(translation_pairs) < 2:
            return None

        translation_pairs = self._project_translation_pairs(
            animation,
            translation_pairs,
        )

        # Multi-keyframe: build a motion path with M/L segments
        if len(translation_pairs) > 2:
            return self._build_translate_path_element(
                animation,
                behavior_id,
                translation_pairs,
            )

        # Simple 2-value: use a relative motion path so PowerPoint interprets
        # the delta in slide coordinates rather than raw EMUs.
        start_dx, start_dy = translation_pairs[0]
        end_dx, end_dy = translation_pairs[-1]
        viewport_w, viewport_h = self._resolve_motion_viewport_px(animation)
        delta_x = (end_dx - start_dx) / viewport_w
        delta_y = (end_dy - start_dy) / viewport_h

        anim_motion = p_elem(
            "animMotion",
            origin="layout",
            path=(
                f"M 0 0 L {self._format_coord(delta_x)} "
                f"{self._format_coord(delta_y)} E"
            ),
            pathEditMode="relative",
            rAng="0",
            ptsTypes="AA",
        )

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

        # ECMA-376 requires a choice element (by/from/to/rCtr) after cBhvr
        p_sub(anim_motion, "rCtr", x="0", y="0")

        return anim_motion

    def _build_translate_path_element(
        self,
        animation: AnimationDefinition,
        behavior_id: int,
        translation_pairs: list[tuple[float, float]],
    ) -> etree._Element:
        """Build ``<p:animMotion>`` with path for multi-keyframe translate."""
        viewport_w, viewport_h = self._resolve_motion_viewport_px(animation)
        start_x, start_y = translation_pairs[0]

        path_pairs = list(translation_pairs)
        key_times = animation.key_times
        calc_mode_value = (
            animation.calc_mode.value
            if isinstance(animation.calc_mode, CalcMode)
            else str(animation.calc_mode).lower()
        )

        if calc_mode_value == CalcMode.PACED.value and len(path_pairs) > 2:
            paced_times = compute_paced_key_times_2d(path_pairs)
            if paced_times is not None:
                key_times = paced_times

        path_pairs = self._retime_translate_pairs(
            pairs=path_pairs,
            key_times=key_times,
            calc_mode=calc_mode_value,
        )

        # Build M/L path string in slide-fraction coordinates
        segments: list[str] = []
        for i, (x_px, y_px) in enumerate(path_pairs):
            dx_px = x_px - start_x
            dy_px = y_px - start_y
            nx = dx_px / viewport_w
            ny = dy_px / viewport_h

            cmd = "M" if i == 0 else "L"
            segments.append(f"{cmd} {self._format_coord(nx)} {self._format_coord(ny)}")

        path = " ".join(segments) + " E"
        pts_types = "A" * len(path_pairs)

        anim_motion = p_elem(
            "animMotion",
            origin="layout",
            path=path,
            pathEditMode="relative",
            rAng="0",
            ptsTypes=pts_types,
        )

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

        # ECMA-376 requires a choice element (by/from/to/rCtr) after cBhvr
        p_sub(anim_motion, "rCtr", x="0", y="0")

        return anim_motion

    @staticmethod
    def _project_translation_pairs(
        animation: AnimationDefinition,
        pairs: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        matrix = animation.motion_space_matrix
        if matrix is None:
            return list(pairs)
        a, b, c, d, _e, _f = matrix
        return [
            (a * x + c * y, b * x + d * y)
            for x, y in pairs
        ]

    def _resolve_motion_viewport_px(
        self,
        animation: AnimationDefinition,
    ) -> tuple[float, float]:
        if animation.motion_viewport_px is not None:
            width_px = max(float(animation.motion_viewport_px[0]), 1.0)
            height_px = max(float(animation.motion_viewport_px[1]), 1.0)
            return (width_px, height_px)

        from svg2ooxml.drawingml.writer import DEFAULT_SLIDE_SIZE

        return (
            max(float(emu_to_px(DEFAULT_SLIDE_SIZE[0])), 1.0),
            max(float(emu_to_px(DEFAULT_SLIDE_SIZE[1])), 1.0),
        )

    @staticmethod
    def _format_coord(value: float) -> str:
        """Format normalised coordinate as a string."""
        if abs(value) < 1e-10:
            return "0"
        return f"{value:.6g}"

    @staticmethod
    def _retime_translate_pairs(
        *,
        pairs: list[tuple[float, float]],
        key_times: list[float] | None,
        calc_mode: CalcMode | str,
        segment_budget: int = 96,
    ) -> list[tuple[float, float]]:
        """Approximate keyTimes/calcMode timing by expanding path vertices."""
        if len(pairs) < 2 or key_times is None or len(key_times) != len(pairs):
            return pairs

        calc_mode_value = (
            calc_mode.value
            if isinstance(calc_mode, CalcMode)
            else str(calc_mode).lower()
        )
        if calc_mode_value == CalcMode.DISCRETE.value:
            return TransformAnimationHandler._expand_discrete_pairs(
                pairs=pairs,
                key_times=key_times,
                segment_budget=segment_budget,
            )

        return TransformAnimationHandler._retime_linear_pairs(
            pairs=pairs,
            key_times=key_times,
            segment_budget=segment_budget,
        )

    @staticmethod
    def _retime_linear_pairs(
        *,
        pairs: list[tuple[float, float]],
        key_times: list[float],
        segment_budget: int,
    ) -> list[tuple[float, float]]:
        if len(pairs) < 2:
            return pairs

        expanded: list[tuple[float, float]] = [pairs[0]]
        for index in range(1, len(pairs)):
            start = pairs[index - 1]
            end = pairs[index]
            duration = max(0.0, key_times[index] - key_times[index - 1])
            segment_count = max(1, int(round(duration * segment_budget)))

            for step in range(1, segment_count + 1):
                t = step / segment_count
                x = start[0] + (end[0] - start[0]) * t
                y = start[1] + (end[1] - start[1]) * t
                expanded.append((x, y))

        return expanded

    @staticmethod
    def _expand_discrete_pairs(
        *,
        pairs: list[tuple[float, float]],
        key_times: list[float],
        segment_budget: int,
    ) -> list[tuple[float, float]]:
        if len(pairs) < 2:
            return pairs

        expanded: list[tuple[float, float]] = [pairs[0]]
        for index in range(1, len(pairs)):
            prev = pairs[index - 1]
            curr = pairs[index]
            duration = max(0.0, key_times[index] - key_times[index - 1])
            slot_count = max(1, int(round(duration * segment_budget)))

            for _ in range(max(0, slot_count - 1)):
                expanded.append(prev)
            expanded.append(curr)

        return expanded

    # ------------------------------------------------------------------ #
    # Matrix (decompose → delegate)                                        #
    # ------------------------------------------------------------------ #

    def _build_matrix_element(
        self,
        animation: AnimationDefinition,
        behavior_id: int,
    ) -> tuple[etree._Element | None, str]:
        """Build animation element from matrix values.

        Returns (element, preset_class) or (None, "entr") on failure.
        """
        from svg2ooxml.common.geometry.matrix import Matrix2D

        if not animation.values:
            return None, "entr"

        matrices: list[Matrix2D] = []
        for raw in animation.values:
            if not isinstance(raw, str):
                return None, "entr"
            tokens = [t for t in re.split(r"[\s,]+", raw.strip()) if t]
            if len(tokens) < 6:
                return None, "entr"
            try:
                values = [float(t) for t in tokens[:6]]
            except ValueError:
                return None, "entr"
            matrices.append(Matrix2D.from_values(*values))

        matrix_type: str | None = None
        staged: list[tuple[str, object | None]] = []

        for matrix in matrices:
            current_type, payload = self._classify_matrix(matrix)
            if current_type is None:
                return None, "entr"
            if matrix_type is None:
                if current_type != "identity":
                    matrix_type = current_type
            else:
                if current_type not in {"identity", matrix_type}:
                    return None, "entr"
            staged.append((current_type, payload))

        if matrix_type is None:
            return None, "entr"

        classified: list[object] = []
        for current_type, payload in staged:
            if current_type == "identity":
                classified.append(self._identity_payload(matrix_type))
            else:
                classified.append(
                    payload
                    if payload is not None
                    else self._identity_payload(matrix_type)
                )

        if matrix_type == "translate":
            pairs = [(float(x), float(y)) for x, y in classified]
            return self._build_translate_element(animation, behavior_id, pairs), "path"
        elif matrix_type == "scale":
            pairs = [(float(x), float(y)) for x, y in classified]
            return self._build_scale_element(animation, behavior_id, pairs), "entr"
        elif matrix_type == "rotate":
            angles = [float(angle) for angle in classified]
            return self._build_rotate_element(animation, behavior_id, angles), "entr"

        return None, "entr"

    # ------------------------------------------------------------------ #
    # Matrix classification                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _classify_matrix(
        matrix: Matrix2D, *, tolerance: float = 1e-6
    ) -> tuple[str | None, object | None]:
        if not all(
            math.isfinite(v)
            for v in (matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f)
        ):
            return (None, None)

        if (
            abs(matrix.a - 1.0) <= tolerance
            and abs(matrix.d - 1.0) <= tolerance
            and abs(matrix.b) <= tolerance
            and abs(matrix.c) <= tolerance
            and abs(matrix.e) <= tolerance
            and abs(matrix.f) <= tolerance
        ):
            return ("identity", None)

        if (
            abs(matrix.a - 1.0) <= tolerance
            and abs(matrix.d - 1.0) <= tolerance
            and abs(matrix.b) <= tolerance
            and abs(matrix.c) <= tolerance
        ):
            return ("translate", (matrix.e, matrix.f))

        if (
            abs(matrix.b) <= tolerance
            and abs(matrix.c) <= tolerance
            and abs(matrix.e) <= tolerance
            and abs(matrix.f) <= tolerance
        ):
            return ("scale", (matrix.a, matrix.d))

        if (
            abs(matrix.e) <= tolerance
            and abs(matrix.f) <= tolerance
            and abs(matrix.c + matrix.b) <= tolerance
            and abs(matrix.a - matrix.d) <= tolerance
            and abs(matrix.a * matrix.a + matrix.b * matrix.b - 1.0) <= tolerance
            and abs(matrix.c * matrix.c + matrix.d * matrix.d - 1.0) <= tolerance
        ):
            angle_deg = math.degrees(math.atan2(matrix.b, matrix.a))
            return ("rotate", angle_deg)

        # Fall through to QR decomposition for composite matrices
        decomposed = TransformAnimationHandler._decompose_matrix(
            matrix, tolerance=tolerance
        )
        if decomposed is not None:
            return decomposed

        return (None, None)

    @staticmethod
    def _decompose_matrix(
        matrix: Matrix2D,
        *,
        tolerance: float = 1e-6,
    ) -> tuple[str, object] | None:
        """Decompose a composite 2D affine matrix via QR decomposition.

        Extracts (translate, angle, scale) and returns the dominant
        non-trivial component as ``(type, payload)``.

        Returns ``None`` if the matrix contains skew (no PPT equivalent)
        or if no dominant component can be identified.
        """
        import logging

        # Extract translation directly
        tx, ty = matrix.e, matrix.f

        # Scale x = length of first column vector
        sx = math.sqrt(matrix.a**2 + matrix.b**2)
        if sx < tolerance:
            return None  # Degenerate matrix

        # Rotation angle from first column
        angle_deg = math.degrees(math.atan2(matrix.b, matrix.a))

        # Determine sy from determinant (preserves sign for reflections)
        det = matrix.a * matrix.d - matrix.b * matrix.c
        sy = det / sx

        # Verify no skew: reconstruct and compare
        cos_a = math.cos(math.radians(angle_deg))
        sin_a = math.sin(math.radians(angle_deg))
        expected_c = -sy * sin_a
        expected_d = sy * cos_a

        if (
            abs(matrix.c - expected_c) > tolerance
            or abs(matrix.d - expected_d) > tolerance
        ):
            logging.getLogger(__name__).debug(
                "Matrix contains skew — cannot decompose for PowerPoint"
            )
            return None

        # Classify which components are non-trivial
        has_translate = abs(tx) > tolerance or abs(ty) > tolerance
        has_rotate = abs(angle_deg) > tolerance
        has_scale = abs(sx - 1.0) > tolerance or abs(sy - 1.0) > tolerance

        # Pick the dominant component
        if has_translate and not has_rotate and not has_scale:
            return ("translate", (tx, ty))
        if has_rotate and not has_translate and not has_scale:
            return ("rotate", angle_deg)
        if has_scale and not has_translate and not has_rotate:
            return ("scale", (sx, sy))

        # Composite: pick dominant based on priority (translate > rotate > scale)
        if has_translate:
            return ("translate", (tx, ty))
        if has_rotate:
            return ("rotate", angle_deg)
        if has_scale:
            return ("scale", (sx, sy))

        return None

    @staticmethod
    def _identity_payload(matrix_type: str) -> object:
        if matrix_type == "translate":
            return (0.0, 0.0)
        if matrix_type == "scale":
            return (1.0, 1.0)
        if matrix_type == "rotate":
            return 0.0
        return (0.0, 0.0)
