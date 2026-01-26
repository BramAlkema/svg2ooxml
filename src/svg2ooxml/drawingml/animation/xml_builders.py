"""lxml-based XML builders for PowerPoint animation timing.

This module provides safe, composable builders for PowerPoint's timing XML
structures (<p:timing>, <p:par>, <a:cBhvr>, <a:tav>, etc.).
"""

from __future__ import annotations

from lxml import etree

from svg2ooxml.drawingml.xml_builder import (
    a_elem,
    a_sub,
    p_elem,
    p_sub,
    to_string,
)

from .constants import SVG2_ANIMATION_NS

__all__ = ["AnimationXMLBuilder"]


class AnimationXMLBuilder:
    """Build PowerPoint animation timing XML using lxml."""

    # ------------------------------------------------------------------ #
    # Top-Level Containers                                               #
    # ------------------------------------------------------------------ #

    def build_timing_container(
        self,
        *,
        timing_id: int,
        fragments: list[str],
        animated_shape_ids: list[str],
    ) -> str:
        """Build <p:timing> root container with mainSeq hierarchy."""
        timing = p_elem("timing")
        tnlst = p_sub(timing, "tnLst")
        
        # 1. tmRoot container
        root_par = p_sub(tnlst, "par")
        root_ctn = p_sub(root_par, "cTn", id=str(timing_id), dur="indefinite", restart="never", nodeType="tmRoot")
        root_child_tn_lst = p_sub(root_ctn, "childTnLst")
        
        # 2. mainSeq container
        seq = p_sub(root_child_tn_lst, "seq", concurrent="1", nextAc="seek")
        seq_ctn = p_sub(seq, "cTn", id=str(timing_id + 1), dur="indefinite", nodeType="mainSeq")
        child_tn_lst = p_sub(seq_ctn, "childTnLst")

        # 3. Append fragments directly to mainSeq
        for fragment in fragments:
            try:
                from svg2ooxml.drawingml.xml_builder import NS_A, NS_P
                wrapped = f'<root xmlns:a="{NS_A}" xmlns:p="{NS_P}">{fragment}</root>'
                root = etree.fromstring(wrapped)
                if len(root) > 0:
                    child = root[0]
                    # Strip duplicated namespaces
                    for prefix in ("a", "p"):
                        attr_name = f"{{http://www.w3.org/2000/xmlns/}}{prefix}"
                        if attr_name in child.attrib:
                            del child.attrib[attr_name]
                    child_tn_lst.append(child)
            except etree.XMLSyntaxError:
                continue

        # Add navigation triggers to the sequence (Standard PowerPoint behavior)
        prev_cond_lst = p_sub(seq, "prevCondLst")
        prev_cond = p_sub(prev_cond_lst, "cond", evt="onPrev", delay="0")
        p_sub(p_sub(prev_cond, "tgtEl"), "sldTgt")

        next_cond_lst = p_sub(seq, "nextCondLst")
        next_cond = p_sub(next_cond_lst, "cond", evt="onNext", delay="0")
        p_sub(p_sub(next_cond, "tgtEl"), "sldTgt")

        # 4. Build List (p:bldLst)
        if animated_shape_ids:
            bld_lst = p_sub(timing, "bldLst")
            for shape_id in animated_shape_ids:
                p_sub(bld_lst, "bldP", spid=shape_id, grpId="0", animBg="1")

        return to_string(timing)

    def build_par_container(
        self,
        *,
        par_id: int,
        duration_ms: int,
        delay_ms: int,
        child_content: str,
        preset_id: int = 0,
        preset_class: str = "entr",
        preset_subtype: int = 0,
        node_type: str = "withEffect",
    ) -> str:
        """Build <p:par> container with timing and preset metadata."""
        par = p_elem("par")
        ctn = p_sub(
            par, "cTn", 
            id=str(par_id), 
            dur=str(duration_ms), 
            fill="hold", 
            nodeType=node_type,
            presetID=str(preset_id),
            presetClass=preset_class,
            presetSubtype=str(preset_subtype),
            grpId="0"
        )

        # Start condition
        stCondLst = p_sub(ctn, "stCondLst")
        p_sub(stCondLst, "cond", delay=str(delay_ms)) # Revert to original delay, no evt

        # Child timing list
        child_tn_lst = p_sub(ctn, "childTnLst")

        # Parse and append child content
        if child_content and child_content.strip():
            try:
                from svg2ooxml.drawingml.xml_builder import NS_A, NS_P
                wrapped = f'<root xmlns:a="{NS_A}" xmlns:p="{NS_P}">{child_content}</root>'
                root = etree.fromstring(wrapped)
                if len(root) > 0:
                    child = root[0]
                    # Strip duplicated namespaces
                    for prefix in ("a", "p"):
                        attr_name = f"{{http://www.w3.org/2000/xmlns/}}{prefix}"
                        if attr_name in child.attrib:
                            del child.attrib[attr_name]
                    child_tn_lst.append(child)
            except etree.XMLSyntaxError:
                pass

        return to_string(par)

    def build_behavior_core(
        self,
        *,
        behavior_id: int,
        duration_ms: int,
        target_shape: str,
        repeat_count: str | int | None = None,
        accel: int | None = None,
        decel: int | None = None,
        attr_name_list: list[str] | None = None,
    ) -> str:
        """Build <p:cBhvr> common behavior element."""
        cBhvr = p_elem("cBhvr")

        # Common timing node
        ctn_attrs = {
            "id": str(behavior_id),
            "dur": str(duration_ms),
            "fill": "hold",
            "repeatCount": "0",
            "nodeType": "withEffect",
        }

        if repeat_count is not None:
            ctn_attrs["repeatCount"] = str(repeat_count)
        if accel is not None:
            ctn_attrs["accel"] = str(accel)
        if decel is not None:
            ctn_attrs["decel"] = str(decel)

        cTn = p_sub(cBhvr, "cTn", **ctn_attrs)

        # Start condition list for the behavior's internal time node
        stCondLst = p_sub(cTn, "stCondLst")
        p_sub(stCondLst, "cond", delay="0")

        # Target element
        tgtEl = p_sub(cBhvr, "tgtEl")
        spTgt = p_sub(tgtEl, "spTgt", spid=target_shape)

        # Optional attribute list
        if attr_name_list is not None:
            attrNameLst = self.build_attribute_list(attr_name_list)
            cBhvr.append(attrNameLst)

        return to_string(cBhvr)

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