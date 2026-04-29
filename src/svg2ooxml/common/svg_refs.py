"""Small SVG token helpers shared across parser, render, and services."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def local_name(tag: Any) -> str:
    """Return the namespace-free local name for an XML tag."""

    if tag is None:
        return ""
    value = str(tag)
    if "}" in value:
        return value.split("}", 1)[1]
    return value


def namespace_uri(tag: Any) -> str | None:
    """Return the namespace URI from an ElementTree-style tag, when present."""

    if tag is None:
        return None
    value = str(tag)
    if value.startswith("{") and "}" in value:
        namespace = value[1:].split("}", 1)[0]
        return namespace or None
    return None


def namespaced_tag_like(reference: Any, local: str) -> str:
    """Return ``local`` in the same namespace as an XML reference element."""

    namespace = namespace_uri(getattr(reference, "tag", None))
    if namespace:
        return f"{{{namespace}}}{local}"
    return local


def strip_svg_namespace(tag: Any, *, svg_namespace: str = "http://www.w3.org/2000/svg") -> str:
    """Strip the SVG namespace from an ElementTree-style tag when present."""

    value = str(tag)
    prefix = "{" + svg_namespace + "}"
    if value.startswith(prefix):
        return value[len(prefix) :]
    return value


def unwrap_url_reference(token: str | None) -> str | None:
    """Strip a CSS ``url(...)`` wrapper while preserving the referenced value."""

    if not token:
        return None
    value = token.strip()
    if not value:
        return None
    if value.startswith("url(") and value.endswith(")"):
        value = value[4:-1].strip().strip("\"'")
    return value or None


def reference_id(token: str | None) -> str | None:
    """Return a service lookup id from ``url(#id)``, ``#id``, or ``id``."""

    value = unwrap_url_reference(token)
    if not value:
        return None
    if value.startswith("#"):
        return value[1:] or None
    return value


def local_url_id(token: str | None) -> str | None:
    """Return the fragment id only for local URL references."""

    value = unwrap_url_reference(token)
    if value and value.startswith("#"):
        return value[1:] or None
    return None


def href_value(attributes: Mapping[str, str]) -> str | None:
    """Return SVG/XLink href from an attribute mapping, if present."""

    for key in ("href", "{http://www.w3.org/1999/xlink}href"):
        if key in attributes:
            return attributes[key]
    return None


def element_index_by_id(root: Any) -> dict[str, Any]:
    """Build an ``id`` to element lookup for an XML tree."""

    index: dict[str, Any] = {}
    for node in root.iter():
        node_id = node.get("id")
        if node_id:
            index[node_id] = node
    return index


__all__ = [
    "element_index_by_id",
    "href_value",
    "local_name",
    "local_url_id",
    "namespaced_tag_like",
    "namespace_uri",
    "reference_id",
    "strip_svg_namespace",
    "unwrap_url_reference",
]
