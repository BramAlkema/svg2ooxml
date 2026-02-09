"""lxml-based XML builders for PowerPoint animation timing.

This module provides safe, composable builders for PowerPoint's timing XML
structures (<p:timing>, <p:par>, <a:cBhvr>, <a:tav>, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.xml_builder import (
    p_elem,
    p_sub,
)

from .constants import SVG2_ANIMATION_NS

# Register custom namespace for stable prefix in serialization
etree.register_namespace("svg2", SVG2_ANIMATION_NS)

if TYPE_CHECKING:
    from .id_allocator import TimingIDs

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

        # Add metadata attributes
        if metadata:
            for key, value in metadata.items():
                if key.startswith("svg2:"):
                    attr_name = key.split(":", 1)[1]
                    tav.set(f"{{{SVG2_ANIMATION_NS}}}{attr_name}", value)
                else:
                    tav.set(key, value)

        # Append value element
        tav.append(value_elem)

        if accel > 0 or decel > 0:
            tav_pr = p_sub(tav, "tavPr")
            if accel > 0:
                tav_pr.set("accel", str(accel))
            if decel > 0:
                tav_pr.set("decel", str(decel))

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
            root_par, "cTn",
            id=str(ids.root),
            dur="indefinite",
            restart="never",
            nodeType="tmRoot",
        )
        root_child_tn_lst = p_sub(root_ctn, "childTnLst")

        # mainSeq
        seq = p_sub(root_child_tn_lst, "seq", concurrent="1", nextAc="seek")
        seq_ctn = p_sub(
            seq, "cTn",
            id=str(ids.main_seq),
            dur="indefinite",
            nodeType="mainSeq",
        )
        main_child_tn_lst = p_sub(seq_ctn, "childTnLst")

        # Click group wrapper
        click_par = p_sub(main_child_tn_lst, "par")
        click_ctn = p_sub(click_par, "cTn", id=str(ids.click_group), fill="hold")
        click_st = p_sub(click_ctn, "stCondLst")
        p_sub(click_st, "cond", delay="0")
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

        # Build list
        if animated_shape_ids:
            bld_lst = p_sub(timing, "bldLst")
            for shape_id in animated_shape_ids:
                p_sub(bld_lst, "bldP", spid=shape_id, grpId="0", animBg="1")

        return timing

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
            "grpId": "0",
        }
        if preset_id:
            ctn_attrs["presetID"] = str(preset_id)
        if preset_class:
            ctn_attrs["presetClass"] = preset_class
        if preset_subtype is not None and preset_id:
            ctn_attrs["presetSubtype"] = str(preset_subtype)

        ctn = p_sub(par, "cTn", **ctn_attrs)

        st_cond_lst = p_sub(ctn, "stCondLst")
        p_sub(st_cond_lst, "cond", delay=str(delay_ms))

        child_tn_lst = p_sub(ctn, "childTnLst")
        child_tn_lst.append(child_element)

        return par

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

        # Additive attribute on <p:cBhvr> itself (not on cTn)
        if additive == "sum":
            cBhvr.set("additive", "sum")

        # Map fill_mode
        ppt_fill = "hold"
        if fill_mode == "remove":
            ppt_fill = "remove"

        # Map repeat_count — omit for default (play once)
        ppt_repeat: str | None = None
        if repeat_count == "indefinite":
            ppt_repeat = "indefinite"
        elif repeat_count is not None:
            try:
                n = int(repeat_count)
                if n > 1:
                    ppt_repeat = str(n * 1000)
            except (ValueError, TypeError):
                pass

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

        cTn = p_sub(cBhvr, "cTn", **ctn_attrs)

        st_cond_lst = p_sub(cTn, "stCondLst")
        p_sub(st_cond_lst, "cond", delay="0")

        tgt_el = p_sub(cBhvr, "tgtEl")
        p_sub(tgt_el, "spTgt", spid=target_shape)

        if attr_name_list is not None:
            cBhvr.append(self.build_attribute_list(attr_name_list))

        return cBhvr

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