"""Geometry and style-context helpers for the public SVG parser."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.core.parser.colors.parsing import parse_color
from svg2ooxml.core.parser.style_context import StyleContext as ParserStyleContext
from svg2ooxml.core.parser.style_context import resolve_viewport
from svg2ooxml.core.parser.units import viewbox_to_px
from svg2ooxml.core.traversal.viewbox import parse_viewbox_attribute


class SVGParserGeometryMixin:
    def _strip_whitespace(self, element: etree._Element) -> None:
        """Remove leading/trailing whitespace from text nodes."""
        if element.text:
            element.text = element.text.strip()
        if element.tail:
            element.tail = element.tail.strip()
        for child in element:
            self._strip_whitespace(child)

    def _extract_dimensions(
        self, root: etree._Element
    ) -> tuple[float | None, float | None]:
        width_px, height_px = resolve_viewport(
            root,
            self._unit_converter,
            default_width=800.0,
            default_height=600.0,
        )
        viewbox = root.get("viewBox")
        if viewbox is None and root.get("width") is None:
            width_px = None
        if viewbox is None and root.get("height") is None:
            height_px = None
        return width_px, height_px

    def _extract_viewbox_scale(
        self,
        root: etree._Element,
        width_px: float | None,
        height_px: float | None,
    ) -> tuple[float, float] | None:
        viewbox_attr = root.get("viewBox")
        if not viewbox_attr or width_px is None or height_px is None:
            return None
        viewbox = self._parse_viewbox(viewbox_attr)
        if viewbox is None:
            return None
        return viewbox_to_px(viewbox, width_px, height_px)

    @staticmethod
    def _extract_root_color(
        root: etree._Element,
    ) -> tuple[float, float, float, float] | None:
        color_attr = root.get("color")
        if not color_attr:
            return None
        return parse_color(color_attr)

    @staticmethod
    def _parse_viewbox(value: str) -> tuple[float, float, float, float] | None:
        try:
            viewbox = parse_viewbox_attribute(value)
        except ValueError:
            return None
        if viewbox is None:
            return None
        return (viewbox.min_x, viewbox.min_y, viewbox.width, viewbox.height)

    def _build_style_context(
        self,
        width_px: float | None,
        height_px: float | None,
    ) -> ParserStyleContext | None:
        if width_px is None or height_px is None:
            return None
        conversion = self._unit_converter.create_context(
            width=width_px,
            height=height_px,
            font_size=12.0,
            parent_width=width_px,
            parent_height=height_px,
        )
        return ParserStyleContext(
            conversion=conversion,
            viewport_width=width_px,
            viewport_height=height_px,
        )


__all__ = ["SVGParserGeometryMixin"]
