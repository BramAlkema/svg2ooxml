"""SVG font conversion helpers (SVG <font> → TTF)."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy

from lxml import etree  # type: ignore[import-untyped]

from svg2ooxml.services.fonts.fontforge_utils import (
    FONTFORGE_AVAILABLE,
    generate_font_bytes,
    open_font,
)

_SVG_NS = "http://www.w3.org/2000/svg"
_XML_NS = "http://www.w3.org/XML/1998/namespace"


def convert_svg_font(
    svg_bytes: bytes,
    *,
    font_id: str | None = None,
) -> bytes | None:
    if not FONTFORGE_AVAILABLE:  # pragma: no cover - optional dependency guard
        return None

    payload = _select_font(svg_bytes, font_id)
    if payload is None:
        return None

    try:
        with open_font(payload, suffix=".svg") as font:
            return generate_font_bytes(font, suffix=".ttf")
    except Exception:
        return None


def _select_font(svg_bytes: bytes, font_id: str | None) -> bytes | None:
    try:
        root = etree.fromstring(svg_bytes)
    except Exception:
        return None

    font_el = None
    if font_id:
        for candidate in _iter_fonts(root):
            if _font_matches_id(candidate, font_id):
                font_el = candidate
                break
    if font_el is None:
        for candidate in _iter_fonts(root):
            font_el = candidate
            break

    if font_el is None:
        return None

    svg_root = etree.Element(f"{{{_SVG_NS}}}svg", nsmap={None: _SVG_NS})
    defs = etree.SubElement(svg_root, f"{{{_SVG_NS}}}defs")
    defs.append(deepcopy(font_el))
    return etree.tostring(svg_root, encoding="utf-8", xml_declaration=True)


def _iter_fonts(root: etree._Element) -> Iterable[etree._Element]:
    fonts = root.xpath(".//svg:font", namespaces={"svg": _SVG_NS})
    if fonts:
        return fonts
    return root.xpath(".//*[local-name()='font']")


def _font_matches_id(font_el: etree._Element, font_id: str) -> bool:
    if font_el.get("id") == font_id:
        return True
    return font_el.get(f"{{{_XML_NS}}}id") == font_id


__all__ = ["convert_svg_font"]
