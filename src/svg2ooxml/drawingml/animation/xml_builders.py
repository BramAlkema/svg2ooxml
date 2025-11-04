"""lxml-based XML builders for PowerPoint animation timing.

This module provides safe, composable builders for PowerPoint's timing XML
structures (<p:timing>, <p:par>, <a:cBhvr>, <a:tav>, etc.).

All animation XML generation should use these builders instead of string
concatenation to ensure proper escaping, namespace handling, and structure.
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
    """Build PowerPoint animation timing XML using lxml.

    Provides methods for building timing structures:
    - Timing containers (<p:timing>)
    - Parallel containers (<p:par>)
    - Common behavior (<a:cBhvr>)
    - Time-animated values (<a:tav>)
    - Attribute lists (<a:attrNameLst>)
    - Start conditions (<p:cond>)

    Example:
        >>> builder = AnimationXMLBuilder()
        >>> par = builder.build_par_container(
        ...     par_id=1001,
        ...     duration_ms=1000,
        ...     delay_ms=0,
        ...     child_content="<a:anim>...</a:anim>"
        ... )
    """

    # ------------------------------------------------------------------ #
    # Top-Level Containers                                               #
    # ------------------------------------------------------------------ #

    def build_timing_container(
        self,
        *,
        timing_id: int,
        fragments: list[str],
    ) -> str:
        """Build <p:timing> root container.

        Args:
            timing_id: Unique ID for timing element
            fragments: List of XML fragment strings (animation sequences)

        Returns:
            Complete <p:timing> XML string

        Example:
            >>> xml = builder.build_timing_container(
            ...     timing_id=1,
            ...     fragments=["<p:par>...</p:par>"]
            ... )
        """
        timing = p_elem("timing")
        tnlst = p_sub(timing, "tnLst")
        par = p_sub(tnlst, "par")

        ctn = p_sub(par, "cTn", id=str(timing_id), dur="indefinite", restart="never", nodeType="tmRoot")

        childTnLst = p_sub(ctn, "childTnLst")

        # Append each fragment as raw XML
        for fragment in fragments:
            # Parse fragment and append to childTnLst
            try:
                frag_elem = etree.fromstring(fragment)
                childTnLst.append(frag_elem)
            except etree.XMLSyntaxError:
                # If fragment is malformed, skip it
                continue

        return to_string(timing)

    def build_par_container(
        self,
        *,
        par_id: int,
        duration_ms: int,
        delay_ms: int,
        child_content: str,
    ) -> str:
        """Build <p:par> container with timing.

        Args:
            par_id: Unique ID for par element
            duration_ms: Duration in milliseconds
            delay_ms: Delay in milliseconds
            child_content: Inner XML content (animation effects)

        Returns:
            Complete <p:par> XML string

        Example:
            >>> xml = builder.build_par_container(
            ...     par_id=1001,
            ...     duration_ms=1000,
            ...     delay_ms=0,
            ...     child_content="<a:animEffect>...</a:animEffect>"
            ... )
        """
        par = p_elem("par")
        ctn = p_sub(par, "cTn", id=str(par_id), dur=str(duration_ms), fill="hold")

        # Start condition (always add, even for delay=0)
        start_elem = self.build_start_condition(delay_ms)
        stCondLst = p_sub(ctn, "stCondLst")
        stCondLst.append(start_elem)

        # Child timing list
        childTnLst = p_sub(ctn, "childTnLst")

        # Parse and append child content
        if child_content and child_content.strip():
            try:
                # Wrap content with namespace declarations for parsing
                from svg2ooxml.drawingml.xml_builder import NS_A, NS_P
                wrapped = f'<root xmlns:a="{NS_A}" xmlns:p="{NS_P}">{child_content}</root>'
                root = etree.fromstring(wrapped)
                # Extract and append the child element
                if len(root) > 0:
                    childTnLst.append(root[0])
            except etree.XMLSyntaxError:
                pass  # Skip malformed content

        return to_string(par)

    # ------------------------------------------------------------------ #
    # Common Behavior                                                    #
    # ------------------------------------------------------------------ #

    def build_behavior_core(
        self,
        *,
        behavior_id: int,
        duration_ms: int,
        target_shape: str,
        repeat_count: str | int | None = None,
        accel: int | None = None,
        decel: int | None = None,
        attribute_list: etree._Element | None = None,
    ) -> str:
        """Build <a:cBhvr> common behavior element.

        Args:
            behavior_id: Unique ID for behavior
            duration_ms: Duration in milliseconds
            target_shape: Target shape ID/reference
            repeat_count: Repeat count (number or "indefinite")
            accel: Acceleration percentage (0-100000)
            decel: Deceleration percentage (0-100000)
            attribute_list: Optional attribute name list element (<a:attrNameLst>)

        Returns:
            XML string for <a:cBhvr>

        Example:
            >>> bhvr = builder.build_behavior_core(
            ...     behavior_id=1002,
            ...     duration_ms=1000,
            ...     target_shape="shape1"
            ... )
        """
        cBhvr = a_elem("cBhvr")

        # Common timing node
        ctn_attrs = {
            "id": str(behavior_id),
            "dur": str(duration_ms),
            "fill": "hold",
        }

        if repeat_count is not None:
            ctn_attrs["repeatCount"] = str(repeat_count)
        if accel is not None:
            ctn_attrs["accel"] = str(accel)
        if decel is not None:
            ctn_attrs["decel"] = str(decel)

        cTn = a_sub(cBhvr, "cTn", **ctn_attrs)

        # Target element
        tgtEl = a_sub(cBhvr, "tgtEl")
        spTgt = a_sub(tgtEl, "spTgt", spid=target_shape)

        # Optional attribute list (for color, numeric, set animations)
        if attribute_list is not None:
            cBhvr.append(attribute_list)

        return to_string(cBhvr)

    # ------------------------------------------------------------------ #
    # Attribute Lists                                                    #
    # ------------------------------------------------------------------ #

    def build_attribute_list(
        self,
        attribute_names: list[str],
    ) -> etree._Element:
        """Build <a:attrNameLst> attribute name list.

        Args:
            attribute_names: List of attribute names

        Returns:
            lxml Element for <a:attrNameLst>

        Example:
            >>> attr_list = builder.build_attribute_list(["ppt_x", "ppt_y"])
        """
        attrNameLst = a_elem("attrNameLst")

        for name in attribute_names:
            attrName = a_sub(attrNameLst, "attrName")
            attrName.text = name

        return attrNameLst

    # ------------------------------------------------------------------ #
    # Time-Animated Values (TAV)                                         #
    # ------------------------------------------------------------------ #

    def build_tav_element(
        self,
        *,
        tm: int,
        value_elem: etree._Element,
        accel: int = 0,
        decel: int = 0,
        metadata: dict[str, str] | None = None,
    ) -> etree._Element:
        """Build <a:tav> time-animated value element.

        Args:
            tm: Time percentage (0-100000)
            value_elem: Value element (<a:val> or similar)
            accel: Acceleration percentage (0-100000)
            decel: Deceleration percentage (0-100000)
            metadata: Optional metadata attributes (for custom svg2: namespace)

        Returns:
            lxml Element for <a:tav>

        Example:
            >>> val = a_elem("val", val="100")
            >>> tav = builder.build_tav_element(
            ...     tm=0,
            ...     value_elem=val,
            ...     accel=0,
            ...     decel=0
            ... )
        """
        tav = a_elem("tav", tm=str(tm))

        # Add metadata attributes (e.g., svg2:spline)
        if metadata:
            for key, value in metadata.items():
                # Handle custom namespace attributes
                if key.startswith("svg2:"):
                    attr_name = key.split(":", 1)[1]
                    tav.set(f"{{{SVG2_ANIMATION_NS}}}{attr_name}", value)
                else:
                    tav.set(key, value)

        # Append value element
        tav.append(value_elem)

        # Add accel/decel if non-zero
        if accel > 0:
            a_sub(tav, "accel", val=str(accel))
        if decel > 0:
            a_sub(tav, "decel", val=str(decel))

        return tav

    # ------------------------------------------------------------------ #
    # Start Conditions                                                   #
    # ------------------------------------------------------------------ #

    def build_start_condition(
        self,
        delay_ms: int,
    ) -> etree._Element:
        """Build <p:cond> start condition element.

        Args:
            delay_ms: Delay in milliseconds

        Returns:
            lxml Element for <p:cond>

        Example:
            >>> cond = builder.build_start_condition(1000)
        """
        cond = p_elem("cond", delay=str(delay_ms))
        return cond

    # ------------------------------------------------------------------ #
    # Helper: Build TAV List Container                                   #
    # ------------------------------------------------------------------ #

    def build_tav_list_container(
        self,
        tav_elements: list[etree._Element],
    ) -> etree._Element:
        """Build <a:tavLst> container with TAV elements.

        Args:
            tav_elements: List of <a:tav> elements

        Returns:
            lxml Element for <a:tavLst>

        Example:
            >>> tav1 = builder.build_tav_element(tm=0, value_elem=...)
            >>> tav2 = builder.build_tav_element(tm=100000, value_elem=...)
            >>> tavLst = builder.build_tav_list_container([tav1, tav2])
        """
        tavLst = a_elem("tavLst")

        for tav in tav_elements:
            tavLst.append(tav)

        return tavLst

    # ------------------------------------------------------------------ #
    # Helper: Build Value Elements                                       #
    # ------------------------------------------------------------------ #

    def build_numeric_value(self, value: str) -> etree._Element:
        """Build <a:val val="..."/> for numeric values.

        Args:
            value: Numeric value as string

        Returns:
            lxml Element for <a:val>
        """
        return a_elem("val", val=value)

    def build_color_value(self, hex_color: str) -> etree._Element:
        """Build <a:val><a:srgbClr val="..."/></a:val> for colors.

        Args:
            hex_color: Color in hex format (without #)

        Returns:
            lxml Element for <a:val> containing <a:srgbClr>
        """
        val = a_elem("val")
        a_sub(val, "srgbClr", val=hex_color)
        return val

    def build_point_value(self, x: str, y: str) -> etree._Element:
        """Build <a:val><a:pt x="..." y="..."/></a:val> for points.

        Args:
            x: X coordinate as string
            y: Y coordinate as string

        Returns:
            lxml Element for <a:val> containing <a:pt>
        """
        val = a_elem("val")
        a_sub(val, "pt", x=x, y=y)
        return val
