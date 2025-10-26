"""Utilities for detecting and splitting multi-page SVG documents."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Iterable, List, Tuple

from lxml import etree as ET


@dataclass(frozen=True)
class SplitPage:
    """Represents a page extracted from a multi-page SVG."""

    content: str
    title: str | None = None


PAGE_MARKER_XPATHS: tuple[str, ...] = (
    ".//*[@data-page]",
    ".//*[@data-slide]",
    ".//*[@class='page']",
    ".//*[@class='slide']",
    ".//*[contains(@class, ' page')]",
    ".//*[contains(@class, ' slide')]",
    ".//*[@id[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'page')]]",
    ".//*[@id[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'slide')]]",
)


def split_svg_into_pages(svg_content: str) -> List[SplitPage]:
    """Split SVG content into multiple pages based on simple heuristics."""

    try:
        root = ET.fromstring(svg_content.encode("utf-8"))
    except ET.XMLSyntaxError:
        return [SplitPage(content=svg_content)]

    explicit_pages = _find_explicit_pages(root)
    if explicit_pages:
        return explicit_pages

    nested_svgs = _find_nested_svg_pages(root)
    if nested_svgs:
        return nested_svgs

    return [SplitPage(content=svg_content)]


def _find_explicit_pages(root: ET.Element) -> List[SplitPage]:
    """Detect pages using explicit marker attributes."""

    pages: list[SplitPage] = []
    seen_paths: set[str] = set()

    for xpath in PAGE_MARKER_XPATHS:
        try:
            candidates = root.xpath(xpath)
        except ET.XPathEvalError:
            continue

        for candidate in candidates:
            if not isinstance(candidate, ET._Element):
                continue
            path = candidate.getroottree().getpath(candidate)
            if path in seen_paths:
                continue
            seen_paths.add(path)

            page_content = _wrap_element_as_svg(root, candidate)
            title = _extract_title(candidate)
            pages.append(SplitPage(content=page_content, title=title))

    return pages


def _find_nested_svg_pages(root: ET.Element) -> List[SplitPage]:
    """Detect pages by looking for nested <svg> elements."""

    pages: list[SplitPage] = []
    svg_namespace = _namespace(root)

    for child in root.findall(f".//{{{svg_namespace}}}svg"):
        page_content = ET.tostring(child, encoding="unicode")
        title = _extract_title(child)
        pages.append(SplitPage(content=page_content, title=title))

    return pages


def _wrap_element_as_svg(root: ET.Element, element: ET._Element) -> str:
    """Create a standalone SVG document for the provided element."""

    svg_namespace = _namespace(root)
    page_root = ET.Element(f"{{{svg_namespace}}}svg", nsmap=root.nsmap)
    for key, value in root.attrib.items():
        page_root.set(key, value)

    page_root.append(copy.deepcopy(element))
    return ET.tostring(page_root, encoding="unicode")


def _extract_title(element: ET._Element) -> str | None:
    """Infer a display title from attributes or child elements."""

    preferred_attributes = (
        "data-title",
        "title",
        "aria-label",
        "id",
        "class",
    )
    for attr in preferred_attributes:
        value = element.get(attr)
        if value and value.strip():
            return value.strip()

    for tag in ("title", "desc"):
        child = element.find(f".//{tag}")
        if child is not None and child.text:
            text = child.text.strip()
            if text:
                return text

    return None


def _namespace(element: ET.Element) -> str:
    """Return the SVG namespace for the provided element."""

    if element.tag.startswith("{"):
        return element.tag.split("}", 1)[0][1:]
    return "http://www.w3.org/2000/svg"


__all__ = ["split_svg_into_pages", "SplitPage"]
