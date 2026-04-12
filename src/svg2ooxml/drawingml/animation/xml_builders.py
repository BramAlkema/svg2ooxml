"""lxml-based XML builders for PowerPoint animation timing.

This module provides safe, composable builders for PowerPoint's timing XML
structures (<p:timing>, <p:par>, <a:cBhvr>, <a:tav>, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import (
    NS_P,
    p_elem,
    p_sub,
)

from .constants import SVG2_ANIMATION_NS

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

        # Metadata is currently tracing-only; avoid serializing non-schema attrs.
        if metadata:
            for key, value in metadata.items():
                if key.startswith("svg2:"):
                    continue
                tav.set(key, value)

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
        timing = p_elem("timing")
        tn_lst = p_sub(timing, "tnLst")

        # tmRoot
        root_par = p_sub(tn_lst, "par")
        root_ctn = p_sub(
            root_par,
            "cTn",
            id=str(ids.root),
            dur="indefinite",
            restart="never",
            nodeType="tmRoot",
        )
        root_child_tn_lst = p_sub(root_ctn, "childTnLst")

        # mainSeq
        seq = p_sub(root_child_tn_lst, "seq", concurrent="1", nextAc="seek")
        seq_ctn = p_sub(
            seq,
            "cTn",
            id=str(ids.main_seq),
            dur="indefinite",
            nodeType="mainSeq",
        )
        main_child_tn_lst = p_sub(seq_ctn, "childTnLst")

        # Click group wrapper. PowerPoint-authored decks typically gate the
        # wrapper with an indefinite delay plus an onBegin reference to the
        # main sequence instead of a plain delay=0 condition.
        click_par = p_sub(main_child_tn_lst, "par")
        click_ctn = p_sub(click_par, "cTn", id=str(ids.click_group), fill="hold")
        click_st = p_sub(click_ctn, "stCondLst")
        p_sub(click_st, "cond", delay="indefinite")
        click_begin = p_sub(click_st, "cond", evt="onBegin", delay="0")
        p_sub(click_begin, "tn", val=str(ids.main_seq))
        click_child_tn_lst = p_sub(click_ctn, "childTnLst")

        # Append animation elements
        for elem in animation_elements:
            click_child_tn_lst.append(elem)

        # Navigation triggers
        prev_cond_lst = p_sub(seq, "prevCondLst")
        prev_cond = p_sub(prev_cond_lst, "cond", evt="onPrev", delay="0")
        p_sub(p_sub(prev_cond, "tgtEl"), "sldTgt")

        next_cond_lst = p_sub(seq, "nextCondLst")
        next_cond = p_sub(next_cond_lst, "cond", evt="onNext", delay="0")
        p_sub(p_sub(next_cond, "tgtEl"), "sldTgt")

        # Build list. PowerPoint uses grpId=0 entries for the shape itself and
        # separate non-zero grpId entries for authored animation effects that
        # should surface in the Animation Pane.
        effect_build_entries = self._collect_effect_build_entries(animation_elements)
        if animated_shape_ids or effect_build_entries:
            bld_lst = p_sub(timing, "bldLst")
            for shape_id in animated_shape_ids:
                p_sub(bld_lst, "bldP", spid=shape_id, grpId="0")
            for shape_id, grp_id in effect_build_entries:
                p_sub(bld_lst, "bldP", spid=shape_id, grpId=grp_id, animBg="1")

        return timing

    def _collect_effect_build_entries(
        self,
        animation_elements: list[etree._Element],
    ) -> list[tuple[str, str]]:
        entries: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for par in animation_elements:
            for elem in par.iter():
                if elem.tag != f"{{{NS_P}}}cTn":
                    continue
                grp_id = elem.get("grpId")
                if not grp_id or grp_id == "0":
                    continue
                sp_tgt = elem.find(f".//{{{NS_P}}}spTgt")
                if sp_tgt is None:
                    continue
                shape_id = sp_tgt.get("spid")
                if not shape_id:
                    continue
                key = (shape_id, grp_id)
                if key in seen:
                    continue
                seen.add(key)
                entries.append(key)

        return entries

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
        par = p_elem("par")

        ctn_attrs: dict[str, str] = {
            "id": str(par_id),
            "dur": str(duration_ms),
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
        ppt_repeat = self._repeat_count_value(repeat_count)
        if ppt_repeat is not None:
            ctn_attrs["repeatCount"] = ppt_repeat

        ctn = p_sub(par, "cTn", **ctn_attrs)

        st_cond_lst = p_sub(ctn, "stCondLst")
        if begin_triggers:
            self._append_begin_conditions(
                st_cond_lst=st_cond_lst,
                begin_triggers=begin_triggers,
                fallback_delay_ms=delay_ms,
                default_target_shape=default_target_shape,
            )
        else:
            p_sub(st_cond_lst, "cond", delay=str(delay_ms))

        child_tn_lst = p_sub(ctn, "childTnLst")
        child_tn_lst.append(child_element)

        return par

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
        par = p_elem("par")

        ctn_attrs: dict[str, str] = {
            "id": str(par_id),
            "dur": str(duration_ms),
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
        ppt_repeat = self._repeat_count_value(repeat_count)
        if ppt_repeat is not None:
            ctn_attrs["repeatCount"] = ppt_repeat

        ctn = p_sub(par, "cTn", **ctn_attrs)

        st_cond_lst = p_sub(ctn, "stCondLst")
        if begin_triggers:
            self._append_begin_conditions(
                st_cond_lst=st_cond_lst,
                begin_triggers=begin_triggers,
                fallback_delay_ms=delay_ms,
                default_target_shape=default_target_shape,
            )
        else:
            p_sub(st_cond_lst, "cond", delay=str(delay_ms))

        child_tn_lst = p_sub(ctn, "childTnLst")
        for child_element in child_elements:
            child_tn_lst.append(child_element)

        return par

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
            dur=str(max(1, duration_ms)),
            fill="hold",
        )
        st_cond_lst = p_sub(ctn, "stCondLst")
        p_sub(st_cond_lst, "cond", delay=str(max(0, delay_ms)))
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
        from svg2ooxml.ir.animation import BeginTriggerType

        created = 0
        for trigger in begin_triggers:
            delay_ms = max(0, int(round(trigger.delay_seconds * 1000)))
            trigger_type = trigger.trigger_type

            if trigger_type == BeginTriggerType.TIME_OFFSET:
                p_sub(st_cond_lst, "cond", delay=str(delay_ms))
                created += 1
                continue

            if trigger_type == BeginTriggerType.CLICK:
                cond = p_sub(st_cond_lst, "cond", evt="onClick", delay=str(delay_ms))
                target_shape = trigger.target_element_id or default_target_shape
                if target_shape:
                    tgt_el = p_sub(cond, "tgtEl")
                    p_sub(tgt_el, "spTgt", spid=target_shape)
                created += 1
                continue

            if trigger_type in (
                BeginTriggerType.ELEMENT_BEGIN,
                BeginTriggerType.ELEMENT_END,
            ):
                evt = (
                    "onBegin"
                    if trigger_type == BeginTriggerType.ELEMENT_BEGIN
                    else "onEnd"
                )
                cond = p_sub(st_cond_lst, "cond", evt=evt, delay=str(delay_ms))
                if trigger.target_element_id:
                    tgt_el = p_sub(cond, "tgtEl")
                    p_sub(tgt_el, "spTgt", spid=trigger.target_element_id)
                created += 1
                continue

            # BeginTriggerType.INDEFINITE is not represented natively.
            # It should normally be filtered by policy; ignore if present.

        if created == 0:
            p_sub(st_cond_lst, "cond", delay=str(fallback_delay_ms))

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

        # Additive attribute on <p:cBhvr> itself (not on cTn)
        if additive == "sum":
            cBhvr.set("additive", "sum")

        # Map fill_mode
        ppt_fill = "hold"
        if fill_mode == "remove":
            ppt_fill = "remove"

        # Map repeat_count — omit for default (play once)
        ppt_repeat = self._repeat_count_value(repeat_count)

        ctn_attrs: dict[str, str] = {
            "id": str(behavior_id),
            "dur": str(duration_ms),
            "fill": ppt_fill,
            "nodeType": "withEffect",
        }
        if ppt_repeat is not None:
            ctn_attrs["repeatCount"] = ppt_repeat
        if accel is not None:
            ctn_attrs["accel"] = str(accel)
        if decel is not None:
            ctn_attrs["decel"] = str(decel)
        if auto_reverse:
            ctn_attrs["autoRev"] = "1"

        cTn = p_sub(cBhvr, "cTn", **ctn_attrs)

        st_cond_lst = p_sub(cTn, "stCondLst")
        p_sub(st_cond_lst, "cond", delay="0")

        tgt_el = p_sub(cBhvr, "tgtEl")
        p_sub(tgt_el, "spTgt", spid=target_shape)

        if attr_name_list is not None:
            cBhvr.append(self.build_attribute_list(attr_name_list))

        return cBhvr

    @staticmethod
    def _repeat_count_value(repeat_count: str | int | None) -> str | None:
        if repeat_count == "indefinite":
            return "indefinite"

        if repeat_count is None:
            return None

        try:
            count = int(repeat_count)
        except (TypeError, ValueError):
            return None

        if count > 1:
            return str(count * 1000)
        return None

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
        value after this method returns.
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
