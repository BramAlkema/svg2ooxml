"""Namespace helpers for SVG roots."""

from __future__ import annotations

from collections.abc import Mapping

from lxml import etree

DEFAULT_NAMESPACES: Mapping[str | None, str] = {
    None: "http://www.w3.org/2000/svg",
    "xlink": "http://www.w3.org/1999/xlink",
}


def ensure_namespaces(root: etree._Element) -> dict[str | None, str]:
    """Return a namespace map ensuring SVG defaults exist."""
    namespaces: dict[str | None, str] = {}
    nsmap = getattr(root, "nsmap", None)

    if nsmap:
        namespaces.update(nsmap)

    for prefix, uri in DEFAULT_NAMESPACES.items():
        namespaces.setdefault(prefix, uri)

    return namespaces


__all__ = ["ensure_namespaces", "DEFAULT_NAMESPACES"]
