"""Value XML helpers for PowerPoint animation timing."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.drawingml.xml_builder import p_elem, p_sub


class AnimationValueXMLMixin:
    """Build attribute, value, and TAV fragments."""

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


__all__ = ["AnimationValueXMLMixin"]
