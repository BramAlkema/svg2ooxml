"""lxml-based XML builders for PowerPoint animation timing.

This module provides safe, composable builders for PowerPoint's timing XML
structures (<p:timing>, <p:par>, <a:cBhvr>, <a:tav>, etc.).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import (
    NS_P,
    p_elem,
    p_sub,
)

from .constants import SVG2_ANIMATION_NS
from .timing_conditions import (
    append_begin_conditions,
    append_delay_condition,
    append_end_conditions,
)
from .timing_tree import build_timing_tree as _build_timing_tree
from .timing_values import (
    format_duration_ms,
    repeat_count_value,
)

# Register custom namespace for stable prefix in serialization
etree.register_namespace("svg2", SVG2_ANIMATION_NS)
if TYPE_CHECKING:
    from svg2ooxml.drawingml.animation.id_allocator import TimingIDs
    from svg2ooxml.ir.animation import BeginTrigger

__all__ = ["AnimationXMLBuilder"]


class AnimationXMLBuilder:
    """Build PowerPoint animation timing XML using lxml."""

    def build_attribute_list(
        self,
        attribute_names: list[str],
    ) -> etree._Element:
        """Build <p:attrNameLst> attribute name list."""
        attrNameLst = p_elem("attrNameLst")

        for name in attribute_names:
            elem = p_sub(attrNameLst, "attrName")
            elem.text = name

        return attrNameLst

    def build_tav_element(
        self,
        *,
        tm: int,
        value_elem: etree._Element,
        accel: int = 0,
        decel: int = 0,
        metadata: dict[str, str] | None = None,
    ) -> etree._Element:
        """Build <p:tav> time-animated value element."""
        tav = p_elem("tav", tm=str(tm))

        # Metadata is tracing-only. Do not serialize arbitrary attributes into
        # schema-owned PPT timing XML.

        # Append value element
        tav.append(value_elem)

        return tav

    def build_tav_list_container(
        self,
        tav_elements: list[etree._Element],
    ) -> etree._Element:
        """Build <p:tavLst> container."""
        tavLst = p_elem("tavLst")
        for tav in tav_elements:
            tavLst.append(tav)
        return tavLst

    def build_numeric_value(self, value: str) -> etree._Element:
        """Build <p:val><p:fltVal val="..."/></p:val> for numeric values."""
        val = p_elem("val")
        p_sub(val, "fltVal", val=value)
        return val

    def build_color_value(self, hex_color: str) -> etree._Element:
        """Build <p:val><p:clr><p:srgbClr val="..."/></p:clr></p:val>."""
        val = p_elem("val")
        clr = p_sub(val, "clr")
        p_sub(clr, "srgbClr", val=hex_color)
        return val

    def build_point_value(self, x: str, y: str) -> etree._Element:
        """Build <p:val><p:pt x="..." y="..."/></p:val>."""
        val = p_elem("val")
        p_sub(val, "pt", x=x, y=y)
        return val

    # ------------------------------------------------------------------ #
    # Top-Level Containers                                               #
    # ------------------------------------------------------------------ #

    def build_timing_tree(
        self,
        *,
        ids: TimingIDs,
        animation_elements: list[etree._Element],
        animated_shape_ids: list[str],
    ) -> etree._Element:
        """Build ECMA-376 compliant ``<p:timing>`` tree.

        Returns the root element *without* serializing — the caller is
        responsible for calling ``to_string()`` once at the end.

        Structure::

            <p:timing>
              <p:tnLst>
                <p:par>
                  <p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">
                    <p:childTnLst>
                      <p:seq concurrent="1" nextAc="seek">
                        <p:cTn id="2" dur="indefinite" nodeType="mainSeq">
                          <p:childTnLst>
                            <p:par>                        ← click group
                              <p:cTn id="3" fill="hold">
                                <p:stCondLst>
                                  <p:cond delay="0"/>
                                </p:stCondLst>
                                <p:childTnLst>
                                  ...animation <p:par> elements...
                                </p:childTnLst>
                              </p:cTn>
                            </p:par>
                          </p:childTnLst>
                        </p:cTn>
                        <p:prevCondLst>...</p:prevCondLst>
                        <p:nextCondLst>...</p:nextCondLst>
                      </p:seq>
                    </p:childTnLst>
                  </p:cTn>
                </p:par>
              </p:tnLst>
              <p:bldLst>...</p:bldLst>
            </p:timing>
        """
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
        """Build ``<p:par>`` container accepting a child *element*.

        When *preset_id* is ``None`` (or 0) the preset attributes are
        omitted entirely so PowerPoint treats the effect as custom.
        """
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
        """Build a compound ``<p:par>`` by injecting behavior fragments.

        *behaviors* is a sequence of
        :class:`~svg2ooxml.drawingml.animation.oracle.BehaviorFragment`
        instances (or plain ``(name, tokens)`` tuples). Each fragment names
        a file under ``src/svg2ooxml/assets/animation_oracle/emph/behaviors/``
        and a token map for its private placeholders. The compound slot's
        single ``<p:cTn>`` receives every fragment's children as siblings,
        so they all fire simultaneously on the outer click.

        This is the primary emission path when one shape has multiple
        simultaneous SVG animations: the handler aggregates them into one
        fragment list and calls this method once instead of emitting
        multiple sibling ``<p:par>`` elements.

        Duration and ``SHAPE_ID``/``INNER_FILL`` propagate into every
        fragment automatically. Per-fragment tokens (``BEHAVIOR_ID``,
        ``TO_COLOR``, ``ROTATION_BY``, etc.) must be supplied on each
        ``BehaviorFragment.tokens``.
        """
        # Local import to avoid a module-import cycle when the animation
        # package is still being initialised.
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

    def apply_native_timing_overrides(
        self,
        *,
        par: etree._Element,
        repeat_duration_ms: int | None = None,
        restart: str | None = None,
        end_triggers: list[BeginTrigger] | None = None,
        default_target_shape: str | None = None,
    ) -> None:
        """Apply optional SMIL timing fields to a generated animation fragment.

        Handlers build different native structures. This post-pass keeps common
        timing semantics centralized and avoids threading rarely used timing
        fields through every handler path.
        """
        ctn = par.find(f"{{{NS_P}}}cTn")
        if ctn is None:
            return

        if restart in {"always", "whenNotActive", "never"}:
            ctn.set("restart", restart)

        if repeat_duration_ms is not None:
            repeat_duration = format_duration_ms(repeat_duration_ms, minimum=1)
            targets = self._repeat_duration_targets(par, fallback=ctn)
            for target in targets:
                target.set("repeatDur", repeat_duration)

        if end_triggers:
            end_cond_lst = ctn.find(f"{{{NS_P}}}endCondLst")
            if end_cond_lst is None:
                end_cond_lst = p_sub(ctn, "endCondLst")
            self._append_end_conditions(
                end_cond_lst=end_cond_lst,
                end_triggers=end_triggers,
                default_target_shape=default_target_shape,
            )

    @staticmethod
    def _repeat_duration_targets(
        par: etree._Element,
        *,
        fallback: etree._Element,
    ) -> list[etree._Element]:
        targets = [
            ctn
            for ctn in par.iter(f"{{{NS_P}}}cTn")
            if ctn.get("repeatCount") is not None
        ]
        return targets or [fallback]

    def _append_end_conditions(
        self,
        *,
        end_cond_lst: etree._Element,
        end_triggers: list[BeginTrigger],
        default_target_shape: str | None,
    ) -> None:
        """Append native-compatible end conditions from parsed SMIL end tokens."""
        append_end_conditions(
            end_cond_lst=end_cond_lst,
            end_triggers=end_triggers,
            default_target_shape=default_target_shape,
        )

    def build_behavior_core_elem(
        self,
        *,
        behavior_id: int,
        duration_ms: int,
        target_shape: str,
        repeat_count: str | int | None = None,
        fill_mode: str | None = None,
        additive: str | None = None,
        accel: int | None = None,
        decel: int | None = None,
        attr_name_list: list[str] | None = None,
        auto_reverse: bool = False,
        override: str | None = None,
    ) -> etree._Element:
        """Build ``<p:cBhvr>`` common behavior element.

        Parameters
        ----------
        fill_mode:
            SVG fill mode: ``"freeze"`` → ``fill="hold"``,
            ``"remove"`` → ``fill="remove"``.  Defaults to ``"hold"``
            when *None*.
        additive:
            SVG additive mode: ``"sum"`` → ``additive="sum"`` on
            ``<p:cBhvr>``.  ``"replace"`` or *None* omits the
            attribute (PowerPoint default).
        repeat_count:
            SVG repeatCount: *None*/``1`` → omit attribute
            (PowerPoint default, play once), ``"indefinite"`` →
            ``repeatCount="indefinite"``, integer *N* →
            ``repeatCount="{N * 1000}"``.
        """
        cBhvr = p_elem("cBhvr")

        if self._needs_ppt_runtime_context(attr_name_list):
            cBhvr.set("rctx", "PPT")
        if override:
            cBhvr.set("override", override)

        # PPT concurrent animations on the same target stack additively
        # by default — emitting additive="sum" on cBhvr causes broken
        # composition (shape jumps to slide origin). Empirically verified
        # 2026-04-16: never emit this attribute.
        # if additive == "sum":
        #     cBhvr.set("additive", "sum")

        # Map fill_mode
        ppt_fill = "hold"
        if fill_mode == "remove":
            ppt_fill = "remove"

        ctn_attrs: dict[str, str] = {
            "id": str(behavior_id),
            "dur": format_duration_ms(duration_ms),
            "fill": ppt_fill,
            "nodeType": "withEffect",
        }
        ppt_repeat = repeat_count_value(repeat_count)
        if ppt_repeat is not None:
            ctn_attrs["repeatCount"] = ppt_repeat
        if accel is not None:
            ctn_attrs["accel"] = str(accel)
        if decel is not None:
            ctn_attrs["decel"] = str(decel)
        if auto_reverse:
            ctn_attrs["autoRev"] = "1"

        p_sub(cBhvr, "cTn", **ctn_attrs)

        tgt_el = p_sub(cBhvr, "tgtEl")
        p_sub(tgt_el, "spTgt", spid=target_shape)

        if attr_name_list is not None:
            cBhvr.append(self.build_attribute_list(attr_name_list))

        return cBhvr

    @staticmethod
    def _repeat_count_value(repeat_count: str | int | None) -> str | None:
        return repeat_count_value(repeat_count)

    @staticmethod
    def _needs_ppt_runtime_context(attr_name_list: list[str] | None) -> bool:
        """Return True when the behavior targets PPT runtime-only properties."""
        if not attr_name_list:
            return False
        return any(
            name.startswith("ppt_") or name.startswith("style.")
            for name in attr_name_list
        )

    def build_set_elem(
        self,
        *,
        behavior_id: int,
        duration_ms: int,
        target_shape: str,
        ppt_attribute: str,
        fill_mode: str | None = None,
        additive: str | None = None,
        repeat_count: str | int | None = None,
    ) -> etree._Element:
        """Build ``<p:set>`` element with behavior core.

        The caller is responsible for appending ``<p:to>`` with the target
        value after this method returns. Start conditions belong on an outer
        timing container, not on the inner ``<p:cBhvr>/<p:cTn>`` behavior core.
        """
        set_elem = p_elem("set")
        cBhvr = self.build_behavior_core_elem(
            behavior_id=behavior_id,
            duration_ms=duration_ms,
            target_shape=target_shape,
            attr_name_list=[ppt_attribute],
            fill_mode=fill_mode,
            additive=additive,
            repeat_count=repeat_count,
        )
        set_elem.append(cBhvr)
        return set_elem
