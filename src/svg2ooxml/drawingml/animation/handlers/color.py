"""Color animation handler.

Generates PowerPoint color timing XML for fill, stroke, stop-color, etc.
Simple tweens use ``<p:animClr>``, while multi-keyframe sequences are split
into explicit segments because ``animClr`` cannot carry a ``tavLst``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import a_sub, p_elem, p_sub
from svg2ooxml.ir.animation import AnimationType, CalcMode

from ..constants import COLOR_ATTRIBUTE_NAME_MAP, COLOR_ATTRIBUTES
from .base import AnimationHandler

if TYPE_CHECKING:
    from svg2ooxml.ir.animation import AnimationDefinition

__all__ = ["ColorAnimationHandler"]


class ColorAnimationHandler(AnimationHandler):
    """Handler for color animations (fill, stroke, stop-color, etc.)."""

    def can_handle(self, animation: AnimationDefinition) -> bool:
        if animation.animation_type not in {
            AnimationType.ANIMATE,
            AnimationType.ANIMATE_COLOR,
        }:
            return False
        return animation.target_attribute in COLOR_ATTRIBUTES

    def build(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
    ) -> etree._Element | None:
        """Build ``<p:par>`` containing ``<p:animClr>`` with from/to colors."""
        ppt_attribute = self._map_color_attribute(animation.target_attribute)

        if self._should_segment(animation):
            return self._build_segmented_color_animation(
                animation,
                par_id,
                behavior_id,
                ppt_attribute,
            )

        anim_clr = self._build_anim_clr_element(
            behavior_id=behavior_id,
            duration_ms=animation.duration_ms,
            target_shape=animation.element_id,
            ppt_attribute=ppt_attribute,
            from_color=animation.values[0],
            to_color=animation.values[-1],
            additive=animation.additive,
            fill_mode=animation.fill_mode,
            repeat_count=animation.repeat_count,
        )

        return self._xml.build_par_container_elem(
            par_id=par_id,
            duration_ms=animation.duration_ms,
            delay_ms=animation.begin_ms,
            child_element=anim_clr,
            preset_id=7,
            preset_class="emph",
            begin_triggers=animation.begin_triggers,
            default_target_shape=animation.element_id,
            effect_group_id=par_id,
        )

    @staticmethod
    def _should_segment(animation: AnimationDefinition) -> bool:
        return (
            (animation.calc_mode == CalcMode.DISCRETE and len(animation.values) > 1)
            or len(animation.values) > 2
            or animation.key_times is not None
        )

    def _build_anim_clr_element(
        self,
        *,
        behavior_id: int,
        duration_ms: int,
        target_shape: str,
        ppt_attribute: str,
        from_color: str,
        to_color: str,
        additive: str,
        fill_mode: str,
        repeat_count: int | str | None,
    ) -> etree._Element:
        from_hex = self._processor.parse_color(from_color)
        to_hex = self._processor.parse_color(to_color)

        # Build <p:animClr> — clrSpc and dir are required by ECMA-376
        anim_clr = p_elem("animClr", clrSpc="rgb", dir="cw")

        # Behavior core with attribute name list
        cBhvr = self._xml.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=duration_ms,
            target_shape=target_shape,
            attr_name_list=[ppt_attribute],
            additive=additive,
            fill_mode=fill_mode,
            repeat_count=repeat_count,
        )
        anim_clr.append(cBhvr)

        # <p:from><a:srgbClr val="..."/></p:from>
        from_elem = p_sub(anim_clr, "from")
        a_sub(from_elem, "srgbClr", val=from_hex)

        # <p:to><a:srgbClr val="..."/></p:to>
        to_elem = p_sub(anim_clr, "to")
        a_sub(to_elem, "srgbClr", val=to_hex)

        return anim_clr

    def _build_segmented_color_animation(
        self,
        animation: AnimationDefinition,
        par_id: int,
        behavior_id: int,
        ppt_attribute: str,
    ) -> etree._Element:
        key_times = self._tav.resolve_key_times(animation.values, animation.key_times)
        outer_par, outer_children = self._build_outer_container(animation, par_id)

        if animation.calc_mode == CalcMode.DISCRETE and len(animation.values) > 1:
            self._append_discrete_segments(
                outer_children=outer_children,
                animation=animation,
                behavior_id=behavior_id,
                ppt_attribute=ppt_attribute,
                key_times=key_times,
            )
            return outer_par

        segment_durations = self._compute_segment_durations(
            key_times=key_times,
            total_ms=animation.duration_ms,
        )
        delay_acc = int(round(max(0.0, min(1.0, key_times[0])) * animation.duration_ms))
        bid = behavior_id
        last_segment_index = len(animation.values) - 2

        for index in range(last_segment_index + 1):
            seg_anim = self._build_anim_clr_element(
                behavior_id=bid,
                duration_ms=segment_durations[index],
                target_shape=animation.element_id,
                ppt_attribute=ppt_attribute,
                from_color=animation.values[index],
                to_color=animation.values[index + 1],
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
    ) -> None:
        bid = behavior_id
        last_index = len(animation.values) - 1
        total_ms = animation.duration_ms

        for index, raw_color in enumerate(animation.values):
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
            dur=str(animation.duration_ms),
            fill="hold",
            nodeType="withEffect",
            grpId=str(par_id),
            presetID="7",
            presetClass="emph",
        )
        self._apply_repeat_count(outer_ctn, animation.repeat_count)

        st_cond_lst = p_sub(outer_ctn, "stCondLst")
        if animation.begin_triggers:
            self._xml._append_begin_conditions(
                st_cond_lst=st_cond_lst,
                begin_triggers=animation.begin_triggers,
                fallback_delay_ms=animation.begin_ms,
                default_target_shape=animation.element_id,
            )
        else:
            p_sub(st_cond_lst, "cond", delay=str(animation.begin_ms))

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
            dur=str(max(1, duration_ms)),
            fill="hold",
        )
        seg_st = p_sub(seg_ctn, "stCondLst")
        p_sub(seg_st, "cond", delay=str(max(0, delay_ms)))
        seg_children = p_sub(seg_ctn, "childTnLst")
        seg_children.append(child_element)
        outer_children.append(seg_par)

    @staticmethod
    def _compute_segment_durations(
        *,
        key_times: list[float],
        total_ms: int,
    ) -> list[int]:
        if len(key_times) < 2:
            return [max(1, total_ms)]

        raw_durations = [
            max(1, int(round((key_times[index + 1] - key_times[index]) * total_ms)))
            for index in range(len(key_times) - 1)
        ]
        covered_ms = int(
            round(
                max(0.0, min(1.0, key_times[-1])) * total_ms
                - max(0.0, min(1.0, key_times[0])) * total_ms
            )
        )
        drift = covered_ms - sum(raw_durations)
        raw_durations[-1] += drift
        raw_durations[-1] = max(1, raw_durations[-1])
        return raw_durations

    @staticmethod
    def _apply_repeat_count(
        ctn: etree._Element,
        repeat_count: int | str | None,
    ) -> None:
        if repeat_count == "indefinite":
            ctn.set("repeatCount", "indefinite")
            return

        if repeat_count is None:
            return

        try:
            count = int(repeat_count)
        except (TypeError, ValueError):
            return

        if count > 1:
            ctn.set("repeatCount", str(count * 1000))

    def _map_color_attribute(self, attribute: str) -> str:
        """Map SVG color attribute to PowerPoint attribute name."""
        return COLOR_ATTRIBUTE_NAME_MAP.get(attribute, "fillClr")
