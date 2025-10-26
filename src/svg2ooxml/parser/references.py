"""Namespace collection and external reference detection."""

from __future__ import annotations

from collections.abc import Iterable

from lxml import etree

from .validators import ensure_namespaces

EXTERNAL_PROTOCOLS: tuple[str, ...] = ("http://", "https://", "file://")


def collect_namespaces(root: etree._Element) -> dict[str | None, str]:
    """Return the namespace map with SVG defaults ensured."""
    return ensure_namespaces(root)


def has_external_references(root: etree._Element) -> bool:
    """Detect references to external resources inside the SVG."""
    for element in _iter_elements(root):
        href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")
        if href and href.startswith(EXTERNAL_PROTOCOLS):
            return True

        font_family = element.get("font-family")
        if font_family and "url(" in font_family:
            return True

        local_tag = element.tag.split("}")[-1]
        if local_tag == "style":
            style_content = element.text or ""
            if "url(" in style_content or "@import" in style_content:
                return True

    return False


def _iter_elements(root: etree._Element) -> Iterable[etree._Element]:
    yield root
    yield from root.iterdescendants()


__all__ = ["collect_namespaces", "has_external_references", "EXTERNAL_PROTOCOLS"]
