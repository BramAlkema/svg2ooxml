"""Small SVG token helpers shared across parser, render, and services."""

from __future__ import annotations

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


__all__ = [
    "local_name",
    "local_url_id",
    "namespace_uri",
    "reference_id",
    "unwrap_url_reference",
]
