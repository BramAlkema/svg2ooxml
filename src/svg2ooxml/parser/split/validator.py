"""Structural validation helpers mirroring svg2pptx split parser."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.parser.validators.structure import ensure_svg_root, has_basic_dimensions


class SVGValidator:
    """Perform lightweight SVG root validation with logging."""

    def __init__(self, logger, attribute_checker) -> None:
        self._logger = logger
        self._attribute_checker = attribute_checker

    def validate(self, svg_root: etree._Element) -> None:
        ensure_svg_root(svg_root)
        if not self._attribute_checker(svg_root):
            self._logger.warning("SVG element missing standard attributes (width, height, viewBox)")


__all__ = ["SVGValidator"]
