"""Shared constants for PPTX package assembly."""

from __future__ import annotations

from pathlib import Path

from lxml import etree as ET

ASSETS_ROOT = Path(__file__).resolve().parent.parent / "assets" / "pptx_scaffold"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_DOC_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
THEME_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
THEME_FAMILY_NS = "http://schemas.microsoft.com/office/thememl/2012/main"
ET.register_namespace("thm15", THEME_FAMILY_NS)
MASK_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
MASK_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.drawingml.mask+xml"
FONT_STYLE_TAGS: dict[str, str] = {
    "regular": "regular",
    "bold": "bold",
    "italic": "italic",
    "boldItalic": "boldItalic",
}
FONT_STYLE_ORDER: tuple[str, ...] = ("regular", "bold", "italic", "boldItalic")
ALLOWED_SLIDE_SIZE_MODES = {"multipage", "same"}


__all__ = [
    "ALLOWED_SLIDE_SIZE_MODES",
    "ASSETS_ROOT",
    "CONTENT_NS",
    "FONT_STYLE_ORDER",
    "FONT_STYLE_TAGS",
    "MASK_CONTENT_TYPE",
    "MASK_REL_TYPE",
    "P_NS",
    "R_DOC_NS",
    "REL_NS",
    "THEME_FAMILY_NS",
    "THEME_NS",
]
