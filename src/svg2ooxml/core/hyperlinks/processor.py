"""Hyperlink processing helpers for the core IR pipeline."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from lxml import etree

from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.core.parser.xml_utils import children
from svg2ooxml.core.pipeline.navigation import NavigationSpec, parse_svg_navigation


class HyperlinkProcessor:
    """Extract navigation metadata from hyperlink elements."""

    def __init__(self, logger, child_iter: Callable[[etree._Element], Iterable[etree._Element]] | None = None) -> None:
        self._logger = logger
        self._children = child_iter or children

    def resolve_navigation(self, element: etree._Element) -> NavigationSpec | None:
        href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")
        attrs = self._extract_navigation_attributes(element)
        tooltip = self._extract_tooltip(element)
        try:
            return parse_svg_navigation(href, attrs, tooltip)
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.warning("Failed to parse navigation attributes: %s", exc)
            return None

    def resolve_inline_navigation(self, element: etree._Element) -> NavigationSpec | None:
        href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")
        attrs = self._extract_navigation_attributes(element)
        tooltip = self._extract_tooltip(element)
        try:
            return parse_svg_navigation(href, attrs, tooltip)
        except Exception as exc:  # pragma: no cover - defensive
            self._logger.warning("Failed to parse inline navigation attributes: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_navigation_attributes(self, element: etree._Element) -> dict[str, str]:
        attrs: dict[str, str] = {}
        for name in (
            "data-slide",
            "data-jump",
            "data-bookmark",
            "data-custom-show",
            "data-visited",
        ):
            value = element.get(name)
            if value is not None:
                attrs[name] = value
        return attrs

    def _extract_tooltip(self, element: etree._Element) -> str | None:
        for child in self._children(element):
            tag = local_name(child.tag)
            if tag != "title":
                continue
            tooltip = self._collect_text(child)
            if tooltip:
                return tooltip
        return None

    def _collect_text(self, element: etree._Element) -> str:
        parts: list[str] = []
        if element.text:
            parts.append(element.text)
        for child in self._children(element):
            parts.append(self._collect_text(child))
            if child.tail:
                parts.append(child.tail)
        if element.tail:
            parts.append(element.tail)
        return "".join(parts).strip()

__all__ = ["HyperlinkProcessor"]
