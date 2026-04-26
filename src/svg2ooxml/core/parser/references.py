"""Namespace collection and external reference detection."""

from __future__ import annotations

import re
from collections.abc import Iterable

from lxml import etree

from .validators import ensure_namespaces

EXTERNAL_PROTOCOLS: tuple[str, ...] = ("http://", "https://", "ftp://", "file://")
URL_REFERENCE_RE = re.compile(r"url\(\s*['\"]?(?P<url>[^'\"\)]+)", re.IGNORECASE)


def collect_namespaces(root: etree._Element) -> dict[str | None, str]:
    """Return the namespace map with SVG defaults ensured."""
    return ensure_namespaces(root)


def has_external_references(root: etree._Element) -> bool:
    """Detect references to external resources inside the SVG."""
    for element in _iter_elements(root):
        href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")
        if href and _is_external_reference(href):
            return True

        font_family = element.get("font-family")
        if font_family and _contains_url_reference(font_family):
            return True

        style = element.get("style")
        if style and _contains_external_url(style):
            return True

        local_tag = element.tag.split("}")[-1]
        if local_tag == "style":
            style_content = element.text or ""
            if _contains_external_url(style_content):
                return True

    return False


def _iter_elements(root: etree._Element) -> Iterable[etree._Element]:
    yield root
    yield from root.iterdescendants()


def _is_external_reference(value: str) -> bool:
    return value.strip().lower().startswith(EXTERNAL_PROTOCOLS)


def _contains_url_reference(value: str) -> bool:
    return "url(" in value.lower()


def _contains_external_url(value: str) -> bool:
    lowered = value.lower()
    if "@import" in lowered:
        return True
    return any(
        _is_external_reference(match.group("url"))
        for match in URL_REFERENCE_RE.finditer(value)
    )


__all__ = ["collect_namespaces", "has_external_references", "EXTERNAL_PROTOCOLS"]
