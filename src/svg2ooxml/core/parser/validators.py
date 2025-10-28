"""Validator helpers for parser modules."""

from __future__ import annotations

from collections.abc import Mapping

from lxml import etree

DEFAULT_NAMESPACES: Mapping[str | None, str] = {
    None: "http://www.w3.org/2000/svg",
    "xlink": "http://www.w3.org/1999/xlink",
}


def ensure_namespaces(root: etree._Element) -> dict[str | None, str]:
    namespaces: dict[str | None, str] = {}
    nsmap = getattr(root, "nsmap", None)
    if nsmap:
        namespaces.update(nsmap)
    for prefix, uri in DEFAULT_NAMESPACES.items():
        namespaces.setdefault(prefix, uri)
    return namespaces


def ensure_svg_root(root: etree._Element) -> None:
    local_tag = root.tag.split("}")[-1]
    if local_tag != "svg":
        raise ValueError(f"Root element is '{local_tag}', expected 'svg'")


def has_basic_dimensions(root: etree._Element) -> bool:
    width = root.get("width")
    height = root.get("height")
    view_box = root.get("viewBox")
    return (width is not None and height is not None) or view_box is not None


__all__ = [
    "DEFAULT_NAMESPACES",
    "ensure_namespaces",
    "ensure_svg_root",
    "has_basic_dimensions",
]
