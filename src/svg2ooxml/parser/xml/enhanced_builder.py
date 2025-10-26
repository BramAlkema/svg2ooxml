"""Minimal but functional XML builder for DrawingML elements.

The svg2pptx project ships with a large ``EnhancedXMLBuilder`` that offers a
fluent interface for constructing OpenXML payloads.  For the svg2ooxml port we
start with a lightweight implementation that focuses on safely creating
namespaced elements while keeping the API surface familiar.  Additional helper
methods can be layered on as the batch/mapping stack comes online.
"""


from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from lxml import etree


DEFAULT_NSMAP: Mapping[str | None, str] = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


@dataclass(slots=True)
class EnhancedXMLBuilder:
    """Utility for creating namespaced XML elements.

    The builder intentionally stays small – it exposes convenience helpers for
    creating elements and subelements with the common Presentation ML / Drawing
    ML namespaces.  Future work can extend this class with higher-level shape
    builders while reusing the core namespace handling provided here.
    """

    nsmap: Mapping[str | None, str] = field(default_factory=lambda: dict(DEFAULT_NSMAP))

    def element(self, qname: str, attrib: Mapping[str, str] | None = None, **extra: str) -> etree._Element:
        """Create a new element for the given qualified name.

        ``qname`` accepts "prefix:local" or bare tags (in which case the
        default namespace is used if present).  Additional keyword arguments are
        merged into the attributes mapping to make simple element creation terse.
        """

        tag = self._qualify(qname)
        element = etree.Element(tag, nsmap=self.nsmap)
        for key, value in (attrib or {}).items():
            element.set(key, str(value))
        for key, value in extra.items():
            element.set(key, str(value))
        return element

    def subelement(
        self,
        parent: etree._Element,
        qname: str,
        attrib: Mapping[str, str] | None = None,
        **extra: str,
    ) -> etree._Element:
        """Create a child element and append it to *parent*."""

        child = self.element(qname, attrib, **extra)
        parent.append(child)
        return child

    def shape_tree(self) -> etree._Element:
        """Create an empty presentation shape tree (``p:spTree``)."""

        return self.element("p:spTree")

    def clone(self, element: etree._Element) -> etree._Element:
        """Return a deep copy of *element* for convenience."""

        return etree.fromstring(etree.tostring(element))

    # ------------------------------------------------------------------
    # DrawingML helpers
    # ------------------------------------------------------------------

    def create_shape(
        self,
        name: str,
        *,
        shape_id: int = 1,
        x: int = 0,
        y: int = 0,
        width: int = 914400,
        height: int = 914400,
    ) -> etree._Element:
        """Create a basic ``p:sp`` shape with positioning metadata."""

        shape = self.element("p:sp")
        nv_sp_pr = self.subelement(shape, "p:nvSpPr")
        c_nv_pr = self.subelement(nv_sp_pr, "p:cNvPr", id=str(shape_id), name=name)
        self.subelement(nv_sp_pr, "p:cNvSpPr")
        self.subelement(nv_sp_pr, "p:nvPr")

        sp_pr = self.subelement(shape, "p:spPr")
        xfrm = self.subelement(sp_pr, "a:xfrm")
        self.subelement(xfrm, "a:off", x=str(x), y=str(y))
        self.subelement(xfrm, "a:ext", cx=str(width), cy=str(height))
        return shape

    def create_text_body(self, paragraphs: Sequence[str] | None = None) -> etree._Element:
        """Create a simple ``a:txBody`` with the provided paragraph texts."""

        tx_body = self.element("a:txBody")
        self.subelement(tx_body, "a:bodyPr")
        self.subelement(tx_body, "a:lstStyle")
        if paragraphs:
            for text in paragraphs:
                p = self.subelement(tx_body, "a:p")
                run = self.subelement(p, "a:r")
                self.subelement(run, "a:t").text = text
        else:
            self.subelement(self.subelement(tx_body, "a:p"), "a:endParaRPr")
        return tx_body

    def attach_text_body(self, shape: etree._Element, paragraphs: Sequence[str] | None = None) -> None:
        tx_body = self.create_text_body(paragraphs)
        shape.append(tx_body)

    def create_picture(
        self,
        name: str,
        *,
        embed: str,
        pic_id: int = 1,
        descr: str | None = None,
    ) -> etree._Element:
        """Create a picture (``p:pic``) referencing a relationship ``embed`` id."""

        pic = self.element("p:pic")
        nv_pic_pr = self.subelement(pic, "p:nvPicPr")
        self.subelement(nv_pic_pr, "p:cNvPr", id=str(pic_id), name=name, descr=descr or name)
        self.subelement(nv_pic_pr, "p:cNvPicPr")
        self.subelement(nv_pic_pr, "p:nvPr")

        blip_fill = self.subelement(pic, "p:blipFill")
        self.subelement(blip_fill, "a:blip", **{f"{{{DEFAULT_NSMAP['r']}}}embed": embed})
        self.subelement(blip_fill, "a:stretch").append(self.element("a:fillRect"))

        sp_pr = self.subelement(pic, "p:spPr")
        self.subelement(sp_pr, "a:xfrm")
        self.subelement(sp_pr, "a:prstGeom", prst="rect").append(self.element("a:avLst"))
        return pic

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _qualify(self, qname: str) -> str:
        if ":" in qname:
            prefix, local = qname.split(":", 1)
            uri = self.nsmap.get(prefix)
            if uri is None:
                raise ValueError(f"Unknown namespace prefix: {prefix}")
            return f"{{{uri}}}{local}"
        default_uri = self.nsmap.get(None)
        return qname if default_uri is None else f"{{{default_uri}}}{qname}"


__all__ = ["DEFAULT_NSMAP", "EnhancedXMLBuilder"]
