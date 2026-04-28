"""Segmented multi-keyframe color animation helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.animation.timing_conditions import append_delay_condition
from svg2ooxml.drawingml.animation.timing_utils import compute_segment_durations_ms
from svg2ooxml.drawingml.animation.timing_values import (
    append_repeat_count,
    format_delay_ms,
    format_duration_ms,
)
from svg2ooxml.drawingml.xml_builder import a_sub, p_elem, p_sub
from svg2ooxml.ir.animation import CalcMode

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition


class ColorSegmentMixin:
    """Segmented color animation helpers used by ``ColorAnimationHandler``."""

    @staticmethod
    def _should_segment(animation: AnimationDefinition) -> bool:
        return (
            (animation.calc_mode == CalcMode.DISCRETE and len(animation.values) > 1)
            or len(animation.values) > 2
            or animation.key_times is not None
        )

    def _build_segmented_color_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        ppt_attribute: str,
    ) -> etree._Element:
        values = list(animation.values)
        key_times = self._tav.resolve_key_times(values, animation.key_times)
        outer_par, outer_children = self._build_outer_container(animation, par_id)

        if animation.calc_mode == CalcMode.DISCRETE and len(values) > 1:
            self._append_discrete_segments(
                outer_children=outer_children,
                animation=animation,
                behavior_id=behavior_id,
                ppt_attribute=ppt_attribute,
                key_times=key_times,
                values=values,
            )
            return outer_par

        segment_durations = compute_segment_durations_ms(
            total_ms=animation.duration_ms,
            n_values=len(values),
            key_times=key_times,
        )
        delay_acc = int(round(max(0.0, min(1.0, key_times[0])) * animation.duration_ms))
        bid = behavior_id
        last_segment_index = len(values) - 2

        for index in range(last_segment_index + 1):
            seg_anim = self._build_anim_clr_element(
                behavior_id=bid,
                duration_ms=segment_durations[index],
                target_shape=animation.element_id,
                ppt_attribute=ppt_attribute,
                from_color=values[index],
                to_color=values[index + 1],
                additive=animation.additive,
                fill_mode=(
                    animation.fill_mode if index == last_segment_index else "freeze"
                ),
                repeat_count=None,
            )
            self._append_child_segment(
                outer_children=outer_children,
                segment_id=bid + 1,
                delay_ms=delay_acc,
                duration_ms=segment_durations[index],
                child_element=seg_anim,
            )
            delay_acc += segment_durations[index]
            bid += 2

        return outer_par

    def _append_discrete_segments(
        self,
        *,
        outer_children: etree._Element,
        animation: AnimationDefinition,
        behavior_id: int,
        ppt_attribute: str,
        key_times: list[float],
        values: list[str],
    ) -> None:
        bid = behavior_id
        last_index = len(values) - 1
        total_ms = animation.duration_ms

        for index, raw_color in enumerate(values):
            set_elem = self._xml.build_set_elem(
                behavior_id=bid,
                duration_ms=1,
                target_shape=animation.element_id,
                ppt_attribute=ppt_attribute,
                additive=animation.additive,
                fill_mode=animation.fill_mode if index == last_index else "freeze",
                repeat_count=None,
            )
            to_elem = p_sub(set_elem, "to")
            clr_val = p_sub(to_elem, "clrVal")
            a_sub(clr_val, "srgbClr", val=self._processor.parse_color(raw_color))
            delay_ms = int(round(max(0.0, min(1.0, key_times[index])) * total_ms))
            self._append_child_segment(
                outer_children=outer_children,
                segment_id=bid + 1,
                delay_ms=delay_ms,
                duration_ms=1,
                child_element=set_elem,
            )
            bid += 2

    def _build_outer_container(
        self,
        animation: AnimationDefinition,
        par_id: int,
    ) -> tuple[etree._Element, etree._Element]:
        outer_par = p_elem("par")
        outer_ctn = p_sub(
            outer_par,
            "cTn",
            id=str(par_id),
            dur=format_duration_ms(animation.duration_ms),
            fill="hold",
            nodeType="withEffect",
            grpId=str(par_id),
            presetID="7",
            presetClass="emph",
        )
        append_repeat_count(outer_ctn, animation.repeat_count)

        st_cond_lst = p_sub(outer_ctn, "stCondLst")
        if animation.begin_triggers:
            self._xml._append_begin_conditions(
                st_cond_lst=st_cond_lst,
                begin_triggers=animation.begin_triggers,
                fallback_delay_ms=animation.begin_ms,
                default_target_shape=animation.element_id,
            )
        else:
            p_sub(st_cond_lst, "cond", delay=format_delay_ms(animation.begin_ms))

        outer_children = p_sub(outer_ctn, "childTnLst")
        return outer_par, outer_children

    @staticmethod
    def _append_child_segment(
        *,
        outer_children: etree._Element,
        segment_id: int,
        delay_ms: int,
        duration_ms: int,
        child_element: etree._Element,
    ) -> None:
        seg_par = p_elem("par")
        seg_ctn = p_sub(
            seg_par,
            "cTn",
            id=str(segment_id),
            dur=format_duration_ms(duration_ms, minimum=1),
            fill="hold",
        )
        seg_st = p_sub(seg_ctn, "stCondLst")
        append_delay_condition(seg_st, delay_ms)
        seg_children = p_sub(seg_ctn, "childTnLst")
        seg_children.append(child_element)
        outer_children.append(seg_par)
