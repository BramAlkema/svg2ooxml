"""Numeric animation handler.

Generates PowerPoint ``<p:anim>`` elements with TAV keyframes for
x, y, width, height, stroke-width, rotate, and other numeric attributes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.animation.constants import (
    ATTRIBUTE_NAME_MAP,
    COLOR_ATTRIBUTES,
    DISCRETE_VISIBILITY_ATTRIBUTES,
    FADE_ATTRIBUTES,
    WIPE_ATTRIBUTES,
)
from svg2ooxml.drawingml.animation.handlers.base import AnimationHandler
from svg2ooxml.drawingml.animation.oracle import default_oracle
from svg2ooxml.drawingml.animation.timing_utils import (
    compute_paced_key_times,
    compute_segment_durations_ms,
    sample_spline_keyframes,
)
from svg2ooxml.drawingml.animation.value_formatters import format_numeric_value
from svg2ooxml.drawingml.xml_builder import NS_P, p_elem, p_sub
from svg2ooxml.ir.animation import AnimationType, BeginTriggerType, CalcMode

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition

__all__ = ["NumericAnimationHandler"]


class NumericAnimationHandler(AnimationHandler):
    """Handler for numeric animations (position, size, rotation, etc.)."""

    _DEFAULT_SLIDE_WIDTH_EMU = 9_144_000
    _DEFAULT_SLIDE_HEIGHT_EMU = 6_858_000
    _LINE_ENDPOINT_ATTRS = {"x1", "x2", "y1", "y2"}

    def can_handle(self, animation: AnimationDefinition) -> bool:
        if animation.animation_type != AnimationType.ANIMATE:
            return False
        attr = animation.target_attribute
        if attr in self._LINE_ENDPOINT_ATTRS:
            return False
        if attr in FADE_ATTRIBUTES:
            return False
        if attr in COLOR_ATTRIBUTES:
            return False
        if attr in DISCRETE_VISIBILITY_ATTRIBUTES:
            return False
        return True

    # Attributes that map to <p:animScale> (size changes)
    _SCALE_ATTRS = {"ppt_h", "ppt_w", "height", "width", "w", "h", "rx", "ry"}
    # Attributes that map to <p:animMotion> (position changes)
    _MOTION_ATTRS = {"ppt_x", "ppt_y", "x", "y", "cx", "cy"}

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element | None:
        """Build ``<p:par>`` with the correct animation element type."""
        if animation.target_attribute in WIPE_ATTRIBUTES:
            return self._build_wipe_entrance(animation, par_id, behavior_id)

        ppt_attribute = self._map_attribute_name(animation.target_attribute)

        if (
            animation.calc_mode == CalcMode.DISCRETE
            and ppt_attribute != "style.visibility"
            and len(animation.values) > 1
        ):
            return self._build_discrete_set_segments(
                animation, par_id, behavior_id, ppt_attribute
            )

        has_non_linear_timing = (
            animation.calc_mode in {CalcMode.DISCRETE, CalcMode.SPLINE}
            or bool(animation.key_splines)
        )

        if (
            ppt_attribute in self._SCALE_ATTRS
            or animation.target_attribute in self._SCALE_ATTRS
        ):
            if (
                self._is_symmetric_scale_pulse(animation, ppt_attribute)
                and not has_non_linear_timing
            ):
                return self._build_scale_pulse_animation(
                    animation, par_id, behavior_id, ppt_attribute
                )
            if len(animation.values) > 2 or animation.key_times or has_non_linear_timing:
                if self._can_build_segmented_scale_animation(animation):
                    return self._build_segmented_scale_animation(
                        animation,
                        par_id,
                        behavior_id,
                        ppt_attribute,
                    )
                return self._build_generic_anim(
                    animation,
                    par_id,
                    behavior_id,
                    ppt_attribute,
                    preset_id=None,
                    preset_class="emph",
                )
            return self._build_scale_animation(
                animation, par_id, behavior_id, ppt_attribute
            )

        is_simple = len(animation.values) <= 2 and not animation.key_times
        if is_simple and not has_non_linear_timing and (
            ppt_attribute in self._MOTION_ATTRS
            or animation.target_attribute in self._MOTION_ATTRS
        ):
            return self._build_position_animation(
                animation, par_id, behavior_id, ppt_attribute
            )

        return self._build_generic_anim(animation, par_id, behavior_id, ppt_attribute)

    def _build_scale_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        ppt_attribute: str,
    ) -> etree._Element:
        """Build ``<p:animScale>`` for width/height changes."""
        values = animation.values
        from_val = float(self._normalize_value(ppt_attribute, values[0]))
        to_val = float(self._normalize_value(ppt_attribute, values[-1]))

        animScale = p_elem("animScale")
        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        animScale.append(cBhvr)
        by_x, by_y = self._scale_by_pair(ppt_attribute, from_val, to_val)
        p_sub(animScale, "by", x=str(by_x), y=str(by_y))
        child_elements = [animScale]
        anchor_motion = self._build_scale_anchor_motion(
            animation=animation,
            ppt_attribute=ppt_attribute,
            start_value=from_val,
            end_value=to_val,
            behavior_id=behavior_id * 10 + 1,
            target_shape=animation.element_id,
            duration_ms=animation.duration_ms,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        if anchor_motion is not None:
            child_elements.append(anchor_motion)

        return self._xml.build_par_container_with_children_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_elements=child_elements,
            preset_id=6,  # Grow emphasis
            preset_class="emph",
            preset_subtype=0,
            node_type="withEffect",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
            effect_group_id=par_id,
        )

    def _build_scale_pulse_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        ppt_attribute: str,
    ) -> etree._Element:
        """Build a symmetric grow/shrink pulse using authored-style animScale."""
        values = animation.values
        start_val = float(self._normalize_value(ppt_attribute, values[0]))
        peak_val = float(self._normalize_value(ppt_attribute, values[1]))

        half_duration_ms = max(1, int(round(animation.duration_ms / 2.0)))
        anim_scale = p_elem("animScale")
        c_bhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=half_duration_ms,
            target_shape=animation.element_id,
            repeat_count=animation.repeat_count,
            fill_mode="remove",
            auto_reverse=True,
        )
        anim_scale.append(c_bhvr)
        by_x, by_y = self._scale_by_pair(ppt_attribute, start_val, peak_val)
        p_sub(anim_scale, "by", x=str(by_x), y=str(by_y))
        child_elements = [anim_scale]
        anchor_motion = self._build_scale_anchor_motion(
            animation=animation,
            ppt_attribute=ppt_attribute,
            start_value=start_val,
            end_value=peak_val,
            behavior_id=behavior_id * 10 + 1,
            target_shape=animation.element_id,
            duration_ms=half_duration_ms,
            fill_mode="remove",
            repeat_count=animation.repeat_count,
            auto_reverse=True,
        )
        if anchor_motion is not None:
            child_elements.append(anchor_motion)

        return self._xml.build_par_container_with_children_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_elements=child_elements,
            preset_id=6,
            preset_class="emph",
            preset_subtype=0,
            node_type="withEffect",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
            effect_group_id=par_id,
        )

    def _build_position_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        ppt_attribute: str,
    ) -> etree._Element:
        """Build ``<p:animMotion>`` for x/y position changes."""
        values = animation.values
        from_val = float(self._normalize_value(ppt_attribute, values[0]))
        to_val = float(self._normalize_value(ppt_attribute, values[-1]))

        is_x = ppt_attribute in ("ppt_x", "x", "cx")
        delta_x = (to_val - from_val) if is_x else 0.0
        delta_y = 0.0 if is_x else (to_val - from_val)
        delta_x, delta_y = self._project_motion_delta(
            animation,
            delta_x,
            delta_y,
        )

        # animMotion path uses slide-relative coordinates.
        slide_w_emu, slide_h_emu = self._resolve_slide_dims_emu(animation)
        path = (
            f"M 0 0 L {delta_x / slide_w_emu:.6f} "
            f"{delta_y / slide_h_emu:.6f} E"
        )

        if self._position_uses_oracle(animation):
            return default_oracle().instantiate(
                "path/motion",
                shape_id=animation.element_id,
                par_id=par_id,
                duration_ms=animation.duration_ms,
                delay_ms=animation.begin_ms,
                BEHAVIOR_ID=behavior_id,
                PATH_DATA=path,
                NODE_TYPE="withEffect",
                INNER_FILL=("hold" if animation.fill_mode == "freeze" else "remove"),
            )

        animMotion = p_elem("animMotion")
        animMotion.set("origin", "layout")
        animMotion.set("path", path)
        animMotion.set("pathEditMode", "relative")
        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        animMotion.append(cBhvr)

        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=animMotion,
            preset_id=0,  # Custom motion
            preset_class="path",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
            effect_group_id=par_id,
        )

    @staticmethod
    def _position_uses_oracle(animation: AnimationDefinition) -> bool:
        """Gate the ``path/motion`` oracle path for numeric position animations.

        The template only emits a single time-offset ``<p:cond>`` and cannot
        express ``additive``, ``repeatCount``, or event-based begin triggers.
        Falls through to ``_build_par_container_elem`` when any of those are
        present.
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

    def _build_generic_anim(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        ppt_attribute: str,
        *,
        preset_id: int | None = 32,
        preset_class: str | None = "emph",
    ) -> etree._Element:
        """Build ``<p:anim>`` for other numeric properties (stroke-width, etc.)."""
        anim = p_elem("anim")
        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            attr_name_list=[ppt_attribute],
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )
        anim.append(cBhvr)

        tav_elements = self._build_tav_list(animation, ppt_attribute)
        tav_lst = self._xml.build_tav_list_container(tav_elements)
        anim.append(tav_lst)

        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=anim,
            preset_id=preset_id,
            preset_class=preset_class,
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
            effect_group_id=par_id,
        )

    @staticmethod
    def _can_build_segmented_scale_animation(
        animation: AnimationDefinition,
    ) -> bool:
        if len(animation.values) < 2:
            return False
        if animation.key_splines:
            return False
        calc_mode = (
            animation.calc_mode.value
            if isinstance(animation.calc_mode, CalcMode)
            else str(animation.calc_mode).lower()
        )
        return calc_mode in {CalcMode.LINEAR.value, CalcMode.PACED.value}

    def _build_segmented_scale_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        ppt_attribute: str,
    ) -> etree._Element:
        values = [
            float(self._normalize_value(ppt_attribute, raw_value))
            for raw_value in animation.values
        ]
        key_times = self._resolve_scale_key_times(values, animation)
        segment_durations = compute_segment_durations_ms(
            total_ms=animation.duration_ms,
            n_values=len(values),
            key_times=key_times,
        )

        delay_acc = int(round(max(0.0, min(1.0, key_times[0])) * animation.duration_ms))
        last_segment_index = len(values) - 2
        child_elements: list[etree._Element] = []
        bid = behavior_id

        for index in range(last_segment_index + 1):
            segment_duration = segment_durations[index]
            fill_mode = animation.fill_mode if index == last_segment_index else "hold"
            segment_children = [
                self._build_scale_element_from_values(
                    animation=animation,
                    behavior_id=bid,
                    ppt_attribute=ppt_attribute,
                    start_value=values[index],
                    end_value=values[index + 1],
                    duration_ms=segment_duration,
                    fill_mode=fill_mode,
                    repeat_count=None,
                )
            ]

            anchor_motion = self._build_scale_anchor_motion(
                animation=animation,
                ppt_attribute=ppt_attribute,
                start_value=values[index],
                end_value=values[index + 1],
                behavior_id=bid + 1,
                target_shape=animation.element_id,
                duration_ms=segment_duration,
                fill_mode=fill_mode,
                repeat_count=None,
            )
            if anchor_motion is not None:
                segment_children.append(anchor_motion)

            child_elements.append(
                self._xml.build_par_container_with_children_elem(
                    par_id=bid + 2,
                    duration_ms=segment_duration,
                    delay_ms=delay_acc,
                    child_elements=segment_children,
                    preset_id=6,
                    preset_class="emph",
                    preset_subtype=0,
                    node_type="withEffect",
                    effect_group_id=bid + 2,
                )
            )
            delay_acc += segment_duration
            bid += 3

        return self._xml.build_par_container_with_children_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_elements=child_elements,
            preset_id=None,
            preset_class=None,
            node_type="withEffect",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
            effect_group_id=par_id,
            repeat_count=animation.repeat_count,
        )

    def _build_scale_element_from_values(
        self,
        *,
        animation: AnimationDefinition,
        behavior_id: int,
        ppt_attribute: str,
        start_value: float,
        end_value: float,
        duration_ms: int,
        fill_mode: str | None,
        repeat_count: int | str | None,
    ) -> etree._Element:
        anim_scale = p_elem("animScale")
        c_bhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=duration_ms,
            target_shape=animation.element_id,
            fill_mode=fill_mode,
            repeat_count=repeat_count,
        )
        anim_scale.append(c_bhvr)
        by_x, by_y = self._scale_by_pair(ppt_attribute, start_value, end_value)
        p_sub(anim_scale, "by", x=str(by_x), y=str(by_y))
        return anim_scale

    @staticmethod
    def _resolve_scale_key_times(
        values: list[float],
        animation: AnimationDefinition,
    ) -> list[float]:
        if len(values) <= 1:
            return [0.0]

        calc_mode = (
            animation.calc_mode.value
            if isinstance(animation.calc_mode, CalcMode)
            else str(animation.calc_mode).lower()
        )
        if calc_mode == CalcMode.PACED.value and len(values) > 2:
            paced_times = compute_paced_key_times(values)
            if paced_times is not None:
                return paced_times

        if animation.key_times is not None and len(animation.key_times) == len(values):
            return list(animation.key_times)

        return [index / (len(values) - 1) for index in range(len(values))]

    @staticmethod
    def _scale_baseline(*values: float) -> float:
        for value in values:
            if abs(value) > 1e-6:
                return abs(value)
        return 1.0

    @staticmethod
    def _is_symmetric_scale_pulse(
        animation: AnimationDefinition,
        ppt_attribute: str,
    ) -> bool:
        """Return True for start→peak→start scale pulses that PowerPoint can
        represent as grow/shrink plus auto-reverse.
        """
        if ppt_attribute not in NumericAnimationHandler._SCALE_ATTRS:
            return False
        if len(animation.values) != 3:
            return False
        if animation.calc_mode == CalcMode.DISCRETE:
            return False
        if animation.key_splines:
            return False
        if animation.key_times and [round(t, 6) for t in animation.key_times] != [
            0.0,
            0.5,
            1.0,
        ]:
            return False
        try:
            start = float(animation.values[0])
            peak = float(animation.values[1])
            end = float(animation.values[2])
        except (TypeError, ValueError):
            return False
        if abs(start - end) > 1e-6:
            return False
        if abs(peak - start) <= 1e-6:
            return False
        return True

    @classmethod
    def _scale_pair(
        cls,
        ppt_attribute: str,
        absolute_value: float,
        baseline: float,
    ) -> tuple[int, int]:
        scale_pct = (
            int(round((absolute_value / baseline) * 100000)) if baseline else 100000
        )
        is_height = ppt_attribute in ("ppt_h", "height", "h", "ry")
        x_pct = 100000 if is_height else scale_pct
        y_pct = scale_pct if is_height else 100000
        return (x_pct, y_pct)

    @classmethod
    def _scale_by_pair(
        cls,
        ppt_attribute: str,
        start_value: float,
        end_value: float,
    ) -> tuple[int, int]:
        """Return PowerPoint's native animScale by percentages.

        In authored PowerPoint XML, ``<p:by>`` is the scale amount applied to the
        current shape, not a delta from 100%. Keep the untouched axis at 100%.
        """
        denominator = abs(start_value)
        if denominator <= 1e-6:
            denominator = cls._scale_baseline(start_value, end_value)
        scale_pct = int(round((end_value / denominator) * 100000))
        is_height = ppt_attribute in ("ppt_h", "height", "h", "ry")
        x_pct = 100000 if is_height else scale_pct
        y_pct = scale_pct if is_height else 100000
        return (x_pct, y_pct)

    def _build_scale_anchor_motion(
        self,
        *,
        animation: AnimationDefinition,
        ppt_attribute: str,
        start_value: float,
        end_value: float,
        behavior_id: int,
        target_shape: str,
        duration_ms: int,
        fill_mode: str | None,
        repeat_count: int | str | None,
        auto_reverse: bool = False,
    ) -> etree._Element | None:
        """Compensate for PowerPoint scaling around shape center.

        SVG width/height changes grow from the shape's top-left origin, while
        PowerPoint animScale grows from the center. Pair a matching motion
        effect with scale so the anchored edge stays in place.
        """
        is_width = ppt_attribute in ("ppt_w", "width", "w")
        is_height = ppt_attribute in ("ppt_h", "height", "h")
        if not is_width and not is_height:
            return None

        delta = (end_value - start_value) / 2.0
        if abs(delta) <= 1e-6:
            return None

        slide_w_emu, slide_h_emu = self._resolve_slide_dims_emu(animation)

        if is_width:
            delta_x, delta_y = self._project_motion_delta(animation, delta, 0.0)
        else:
            delta_x, delta_y = self._project_motion_delta(animation, 0.0, delta)

        path = (
            f"M 0 0 L {delta_x / slide_w_emu:.6f} "
            f"{delta_y / slide_h_emu:.6f} E"
        )

        anim_motion = p_elem("animMotion")
        anim_motion.set("origin", "layout")
        anim_motion.set("path", path)
        anim_motion.set("pathEditMode", "relative")
        c_bhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=duration_ms,
            target_shape=target_shape,
            fill_mode=fill_mode,
            repeat_count=repeat_count,
            auto_reverse=auto_reverse,
        )
        anim_motion.append(c_bhvr)
        return anim_motion

    def _resolve_slide_dims_emu(
        self,
        animation: AnimationDefinition,
    ) -> tuple[float, float]:
        viewport = animation.motion_viewport_px
        if viewport is not None:
            width_px = max(float(viewport[0]), 1.0)
            height_px = max(float(viewport[1]), 1.0)
            return (
                max(float(self._units.to_emu(width_px, axis="x")), 1.0),
                max(float(self._units.to_emu(height_px, axis="y")), 1.0),
            )
        return (
            float(self._DEFAULT_SLIDE_WIDTH_EMU),
            float(self._DEFAULT_SLIDE_HEIGHT_EMU),
        )

    @staticmethod
    def _project_motion_delta(
        animation: AnimationDefinition,
        dx: float,
        dy: float,
    ) -> tuple[float, float]:
        matrix = animation.motion_space_matrix
        if matrix is None:
            return (dx, dy)
        a, b, c, d, _e, _f = matrix
        return (a * dx + c * dy, b * dx + d * dy)

    def _build_discrete_set_segments(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        ppt_attribute: str,
    ) -> etree._Element:
        formatted = [
            self._normalize_value(ppt_attribute, v) for v in animation.values
        ]
        return self._build_discrete_set_sequence(
            animation, par_id, behavior_id, ppt_attribute, formatted
        )

    def _build_wipe_entrance(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element:
        """Build Wipe entrance animation for stroke-dashoffset (line drawing).

        SVG line-drawing effect animates stroke-dashoffset from path length
        to 0. PowerPoint's directional Wipe entrance is the closest native
        reveal effect we can express without dropping into dead-path prLst
        parameters.
        """
        oracle = default_oracle()
        filter_entry = oracle.filter_entry("wipe(right)")
        par = oracle.instantiate(
            "entr/filter_effect",
            shape_id=animation.element_id,
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            PRESET_ID=filter_entry.entrance_preset_id,
            PRESET_SUBTYPE=filter_entry.entrance_preset_subtype,
            FILTER=filter_entry.value,
            SET_BEHAVIOR_ID=behavior_id,
            EFFECT_BEHAVIOR_ID=behavior_id + 1,
        )
        if animation.begin_triggers:
            outer_ctn = par.find(f"{{{NS_P}}}cTn")
            if outer_ctn is not None:
                existing = outer_ctn.find(f"{{{NS_P}}}stCondLst")
                if existing is not None:
                    outer_ctn.remove(existing)
                st_cond_lst = p_elem("stCondLst")
                outer_ctn.insert(0, st_cond_lst)
                self._xml._append_begin_conditions(
                    st_cond_lst=st_cond_lst,
                    begin_triggers=animation.begin_triggers,
                    fallback_delay_ms=animation.begin_ms,
                    default_target_shape=animation.element_id,
                )
        return par

    def _map_attribute_name(self, attribute: str) -> str:
        """Map SVG attribute name to PowerPoint attribute name."""
        return ATTRIBUTE_NAME_MAP.get(attribute, attribute)

    def _normalize_value(self, ppt_attribute: str, value: str) -> str:
        """Normalize numeric value based on attribute type."""
        return self._processor.normalize_numeric_value(
            ppt_attribute, value, unit_converter=self._units
        )

    def _build_tav_list(
        self,
        animation: AnimationDefinition,
        ppt_attribute: str,
    ) -> list[etree._Element]:
        """Build TAV elements for this animation.

        For multi-keyframe (>2 values or explicit key_times), delegates
        to TAVBuilder. For simple 2-value animations, creates from/to
        TAV entries at tm=0 and tm=100000.
        """
        values = animation.values
        key_times = animation.key_times
        normalized = [self._normalize_value(ppt_attribute, v) for v in values]

        # Paced calcMode: compute keyTimes from inter-value distances
        if animation.calc_mode == CalcMode.PACED and len(values) > 2:
            try:
                floats = [float(v) for v in values]
                paced_times = compute_paced_key_times(floats)
                if paced_times is not None:
                    key_times = paced_times
            except (ValueError, TypeError):
                pass  # Fall through to default behavior

        if animation.calc_mode == CalcMode.DISCRETE and (len(values) > 1 or key_times):
            return self._tav.build_discrete_tav_list(
                values=normalized,
                key_times=key_times,
                value_formatter=format_numeric_value,
            )

        if animation.calc_mode == CalcMode.SPLINE and animation.key_splines:
            sampled_values, sampled_times = sample_spline_keyframes(
                values=normalized,
                key_times=key_times,
                key_splines=animation.key_splines,
                attribute_name=animation.target_attribute,
            )
            tav_elements, _ = self._tav.build_tav_list(
                values=sampled_values,
                key_times=sampled_times,
                key_splines=None,
                duration_ms=animation.duration_ms,
                value_formatter=format_numeric_value,
            )
            return tav_elements

        # Multi-keyframe: delegate to TAVBuilder with normalized values
        if len(values) > 2 or key_times:
            tav_elements, _ = self._tav.build_tav_list(
                values=normalized,
                key_times=key_times,
                key_splines=animation.key_splines,
                duration_ms=animation.duration_ms,
                value_formatter=format_numeric_value,
            )
            return tav_elements

        # Simple from/to: create two TAV entries
        from_value = self._normalize_value(ppt_attribute, values[0])
        to_value = self._normalize_value(ppt_attribute, values[-1])

        from_tav = self._xml.build_tav_element(
            tm=0,
            value_elem=format_numeric_value(from_value),
        )
        to_tav = self._xml.build_tav_element(
            tm=100000,
            value_elem=format_numeric_value(to_value),
        )
        return [from_tav, to_tav]
