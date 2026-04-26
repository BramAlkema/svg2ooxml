"""Motion animation handler.

Generates PowerPoint ``<p:animMotion>`` elements with SVG-derived motion
paths for ``<animateMotion>`` animations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.animation.oracle import default_oracle
from svg2ooxml.drawingml.animation.timing_utils import compute_segment_durations_ms
from svg2ooxml.drawingml.xml_builder import p_elem
from svg2ooxml.ir.animation import AnimationType, BeginTriggerType

from . import motion_path
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
        points = motion_path.parse_motion_path(path_value)
        points = motion_path.project_motion_points(points, animation)
        points = motion_path.retime_motion_points(points, animation)

        if len(points) < 2:
            return None

        motion_path_value = motion_path.build_motion_path_string(points, animation)
        rotate_mode = self._resolve_rotate_mode(animation)
        if rotate_mode in {"auto", "auto-reverse"}:
            point_angles = motion_path.sample_path_tangent_angles(points, rotate_mode)
            point_angles = self._apply_element_heading_offset(point_angles, animation)
            exact_initial_angle = motion_path.resolve_exact_initial_tangent_angle(
                path_value,
                animation,
                rotate_mode,
            )
            if exact_initial_angle is not None and point_angles:
                point_angles[0] = exact_initial_angle
            if motion_path.has_dynamic_rotation(point_angles):
                rotation_children = self._build_rotation_segment_children(
                    animation=animation,
                    base_behavior_id=behavior_id,
                    point_angles=point_angles,
                )
                if rotation_children:
                    anim_motion = self._build_anim_motion_element(
                        animation=animation,
                        behavior_id=behavior_id,
                        motion_path=motion_path_value,
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
        if rotation == "0" and self._motion_uses_oracle(animation):
            return default_oracle().instantiate(
                "path/motion",
                shape_id=animation.element_id,
                par_id=par_id,
                duration_ms=animation.duration_ms,
                delay_ms=animation.begin_ms,
                BEHAVIOR_ID=behavior_id,
                PATH_DATA=motion_path_value,
                NODE_TYPE="clickEffect",
                INNER_FILL=("hold" if animation.fill_mode == "freeze" else "remove"),
            )

        anim_motion = self._build_anim_motion_element(
            animation=animation,
            behavior_id=behavior_id,
            motion_path=motion_path_value,
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

    @staticmethod
    def _motion_uses_oracle(animation: AnimationDefinition) -> bool:
        """Gate the ``path/motion`` oracle template to simple start/trigger conditions.

        The template emits a single time-offset ``<p:cond>`` and does not
        express ``additive``, ``repeatCount``, or the ``rAng`` rotation
        attribute. Anything more elaborate falls through to
        ``_build_anim_motion_element`` + ``build_par_container_elem`` which can
        inject those via ``build_behavior_core_elem``.
        """
        if (animation.additive or "replace").lower() == "sum":
            return False
        if animation.repeat_count not in (None, 1, "1"):
            return False
        triggers = animation.begin_triggers
        if triggers:
            if len(triggers) > 1:
                return False
            if triggers[0].trigger_type != BeginTriggerType.TIME_OFFSET:
                return False
        return True

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
            point_angles = motion_path.sample_path_tangent_angles(points, rotate_mode)
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

    @staticmethod
    def _apply_element_heading_offset(
        point_angles: list[float],
        animation: AnimationDefinition,
    ) -> list[float]:
        heading = animation.element_heading_deg
        if heading is None:
            return point_angles
        return [angle - heading for angle in point_angles]

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
