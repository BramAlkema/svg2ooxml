"""Parser for SVG <font> and <font-face> definitions."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass

from lxml import etree  # type: ignore[import-untyped]

from svg2ooxml.ir.fonts import FontFaceRule, FontFaceSrc, SvgFontDefinition

logger = logging.getLogger(__name__)

_SVG_NS = "http://www.w3.org/2000/svg"
_XLINK_NS = "http://www.w3.org/1999/xlink"


@dataclass(frozen=True)
class SvgFontParseResult:
    inline_fonts: list[SvgFontDefinition]
    font_faces: list[FontFaceRule]


class SVGFontParser:
    """Extract inline SVG font definitions and external font-face references."""

    def parse(self, svg_root: etree._Element) -> SvgFontParseResult:
        inline_fonts = self._collect_inline_fonts(svg_root)
        font_faces = self._collect_external_font_faces(svg_root)
        if inline_fonts:
            logger.debug("Found %d inline SVG <font> definition(s).", len(inline_fonts))
        if font_faces:
            logger.debug("Found %d SVG <font-face> reference(s).", len(font_faces))
        return SvgFontParseResult(inline_fonts=inline_fonts, font_faces=font_faces)

    def _collect_inline_fonts(self, svg_root: etree._Element) -> list[SvgFontDefinition]:
        inline_fonts: list[SvgFontDefinition] = []
        for font_el in self._iter_svg_elements(svg_root, "font"):
            font_face = self._first_child(font_el, "font-face")
            if font_face is None:
                continue
            family = font_face.get("font-family")
            if not family:
                continue
            weight = font_face.get("font-weight", "normal")
            style = font_face.get("font-style", "normal")
            svg_data = self._wrap_font(font_el)
            inline_fonts.append(
                SvgFontDefinition(
                    family=family,
                    svg_data=svg_data,
                    weight=weight,
                    style=style,
                    source="inline",
                )
            )
        return inline_fonts

    def _collect_external_font_faces(self, svg_root: etree._Element) -> list[FontFaceRule]:
        font_faces: list[FontFaceRule] = []
        for font_face in self._iter_svg_elements(svg_root, "font-face"):
            parent = font_face.getparent()
            if parent is not None and etree.QName(parent).localname == "font":
                continue
            family = font_face.get("font-family")
            if not family:
                continue
            weight = font_face.get("font-weight", "normal")
            style = font_face.get("font-style", "normal")
            srcs = self._extract_font_face_src(font_face)
            if not srcs:
                continue
            font_faces.append(
                FontFaceRule(
                    family=family,
                    src=tuple(srcs),
                    weight=weight,
                    style=style,
                    display="auto",
                )
            )
        return font_faces

    def _extract_font_face_src(self, font_face: etree._Element) -> list[FontFaceSrc]:
        srcs: list[FontFaceSrc] = []
        for uri in self._iter_svg_elements(font_face, "font-face-uri"):
            href = uri.get(f"{{{_XLINK_NS}}}href") or uri.get("href")
            if not href:
                continue
            srcs.append(FontFaceSrc(url=href, format="svg"))
        return srcs

    def _wrap_font(self, font_el: etree._Element) -> bytes:
        svg_root = etree.Element(f"{{{_SVG_NS}}}svg", nsmap={None: _SVG_NS})
        defs = etree.SubElement(svg_root, f"{{{_SVG_NS}}}defs")
        defs.append(deepcopy(font_el))
        return etree.tostring(svg_root, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def _first_child(element: etree._Element, tag: str) -> etree._Element | None:
        for child in element:
            if etree.QName(child).localname == tag:
                return child
        return None

    @staticmethod
    def _iter_svg_elements(root: etree._Element, tag: str) -> Iterable[etree._Element]:
        return root.xpath(
            f".//svg:{tag}",
            namespaces={"svg": _SVG_NS},
        )


__all__ = ["SVGFontParser", "SvgFontParseResult"]
