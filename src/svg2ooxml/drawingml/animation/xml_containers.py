"""Container XML helpers for PowerPoint animation timing."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import p_elem, p_sub

from .timing_conditions import append_begin_conditions, append_delay_condition
from .timing_tree import build_timing_tree as _build_timing_tree
from .timing_values import format_duration_ms, repeat_count_value

if TYPE_CHECKING:
    from svg2ooxml.drawingml.animation.id_allocator import TimingIDs
    from svg2ooxml.ir.animation import BeginTrigger


class AnimationContainerXMLMixin:
    """Build timing trees and nested ``<p:par>`` containers."""

    def build_timing_tree(
        self,
        *,
        ids: TimingIDs,
        animation_elements: list[etree._Element],
        animated_shape_ids: list[str],
    ) -> etree._Element:
        """Build ECMA-376 compliant ``<p:timing>`` tree."""
        return _build_timing_tree(
            ids=ids,
            animation_elements=animation_elements,
            animated_shape_ids=animated_shape_ids,
        )

    def build_par_container_elem(
        self,
        *,
        par_id: int,
        duration_ms: int,
        delay_ms: int,
        child_element: etree._Element,
        preset_id: int | None = None,
        preset_class: str | None = None,
        preset_subtype: int | None = None,
        node_type: str = "withEffect",
        begin_triggers: list[BeginTrigger] | None = None,
        default_target_shape: str | None = None,
        auto_reverse: bool = False,
        effect_group_id: int | str | None = None,
        repeat_count: int | str | None = None,
    ) -> etree._Element:
        """Build ``<p:par>`` container accepting a child *element*."""
        return self.build_par_container(
            par_id=par_id,
            duration_ms=duration_ms,
            delay_ms=delay_ms,
            child_elements=[child_element],
            preset_id=preset_id,
            preset_class=preset_class,
            preset_subtype=preset_subtype,
            node_type=node_type,
            begin_triggers=begin_triggers,
            default_target_shape=default_target_shape,
            auto_reverse=auto_reverse,
            effect_group_id=effect_group_id,
            repeat_count=repeat_count,
        )

    def build_par_container_with_children_elem(
        self,
        *,
        par_id: int,
        duration_ms: int,
        delay_ms: int,
        child_elements: list[etree._Element],
        preset_id: int | None = None,
        preset_class: str | None = None,
        preset_subtype: int | None = None,
        node_type: str = "withEffect",
        begin_triggers: list[BeginTrigger] | None = None,
        default_target_shape: str | None = None,
        auto_reverse: bool = False,
        effect_group_id: int | str | None = None,
        repeat_count: int | str | None = None,
    ) -> etree._Element:
        """Build ``<p:par>`` containing multiple child timing elements."""
        return self.build_par_container(
            par_id=par_id,
            duration_ms=duration_ms,
            delay_ms=delay_ms,
            child_elements=child_elements,
            preset_id=preset_id,
            preset_class=preset_class,
            preset_subtype=preset_subtype,
            node_type=node_type,
            begin_triggers=begin_triggers,
            default_target_shape=default_target_shape,
            auto_reverse=auto_reverse,
            effect_group_id=effect_group_id,
            repeat_count=repeat_count,
        )

    def build_par_container(
        self,
        *,
        par_id: int,
        duration_ms: int,
        delay_ms: int,
        child_elements: Sequence[etree._Element],
        preset_id: int | None = None,
        preset_class: str | None = None,
        preset_subtype: int | None = None,
        node_type: str = "withEffect",
        begin_triggers: list[BeginTrigger] | None = None,
        default_target_shape: str | None = None,
        auto_reverse: bool = False,
        effect_group_id: int | str | None = None,
        repeat_count: int | str | None = None,
    ) -> etree._Element:
        """Build ``<p:par>`` with a shared cTn/stCondLst/childTnLst shape."""
        par = p_elem("par")
        ctn = p_sub(
            par,
            "cTn",
            **self._par_container_ctn_attrs(
                par_id=par_id,
                duration_ms=duration_ms,
                preset_id=preset_id,
                preset_class=preset_class,
                preset_subtype=preset_subtype,
                node_type=node_type,
                auto_reverse=auto_reverse,
                effect_group_id=effect_group_id,
                repeat_count=repeat_count,
            ),
        )

        self._append_start_conditions(
            ctn=ctn,
            delay_ms=delay_ms,
            begin_triggers=begin_triggers,
            default_target_shape=default_target_shape,
        )

        child_tn_lst = p_sub(ctn, "childTnLst")
        for child_element in child_elements:
            child_tn_lst.append(child_element)

        return par

    def _append_start_conditions(
        self,
        *,
        ctn: etree._Element,
        delay_ms: int,
        begin_triggers: list[BeginTrigger] | None,
        default_target_shape: str | None,
    ) -> None:
        st_cond_lst = p_sub(ctn, "stCondLst")
        if begin_triggers:
            self._append_begin_conditions(
                st_cond_lst=st_cond_lst,
                begin_triggers=begin_triggers,
                fallback_delay_ms=delay_ms,
                default_target_shape=default_target_shape,
            )
            return
        append_delay_condition(st_cond_lst, delay_ms)

    @staticmethod
    def _par_container_ctn_attrs(
        *,
        par_id: int,
        duration_ms: int,
        preset_id: int | None,
        preset_class: str | None,
        preset_subtype: int | None,
        node_type: str,
        auto_reverse: bool,
        effect_group_id: int | str | None,
        repeat_count: int | str | None,
    ) -> dict[str, str]:
        ctn_attrs: dict[str, str] = {
            "id": str(par_id),
            "dur": format_duration_ms(duration_ms),
            "fill": "hold",
            "nodeType": node_type,
            "grpId": (str(effect_group_id) if effect_group_id is not None else "0"),
        }
        if preset_id:
            ctn_attrs["presetID"] = str(preset_id)
        if preset_class:
            ctn_attrs["presetClass"] = preset_class
        if preset_subtype is not None and preset_id:
            ctn_attrs["presetSubtype"] = str(preset_subtype)
        if auto_reverse:
            ctn_attrs["autoRev"] = "1"
        ppt_repeat = repeat_count_value(repeat_count)
        if ppt_repeat is not None:
            ctn_attrs["repeatCount"] = ppt_repeat
        return ctn_attrs

    def build_compound_par(
        self,
        *,
        shape_id: str | int,
        par_id: int,
        duration_ms: int,
        delay_ms: int = 0,
        behaviors: list,
    ) -> etree._Element:
        """Build a compound ``<p:par>`` by injecting behavior fragments."""
        # Local import avoids a module-import cycle while animation initializes.
        from svg2ooxml.drawingml.animation.oracle import (
            BehaviorFragment,
            default_oracle,
        )

        normalised: list = []
        for item in behaviors:
            if isinstance(item, BehaviorFragment):
                normalised.append(item)
            else:
                name, tokens = item
                normalised.append(BehaviorFragment(name=name, tokens=tokens))

        return default_oracle().instantiate_compound(
            shape_id=shape_id,
            par_id=par_id,
            duration_ms=duration_ms,
            delay_ms=delay_ms,
            behaviors=normalised,
        )

    def build_delayed_child_par(
        self,
        *,
        par_id: int,
        delay_ms: int,
        duration_ms: int,
        child_element: etree._Element,
    ) -> etree._Element:
        """Build a child ``<p:par>`` wrapper with its own start delay."""
        par = p_elem("par")
        ctn = p_sub(
            par,
            "cTn",
            id=str(par_id),
            dur=format_duration_ms(duration_ms, minimum=1),
            fill="hold",
        )
        st_cond_lst = p_sub(ctn, "stCondLst")
        append_delay_condition(st_cond_lst, delay_ms)
        child_tn_lst = p_sub(ctn, "childTnLst")
        child_tn_lst.append(child_element)
        return par

    def _append_begin_conditions(
        self,
        *,
        st_cond_lst: etree._Element,
        begin_triggers: list[BeginTrigger],
        fallback_delay_ms: int,
        default_target_shape: str | None,
    ) -> None:
        """Append start conditions from parsed begin triggers."""
        append_begin_conditions(
            st_cond_lst=st_cond_lst,
            begin_triggers=begin_triggers,
            fallback_delay_ms=fallback_delay_ms,
            default_target_shape=default_target_shape,
        )


__all__ = ["AnimationContainerXMLMixin"]
