"""Hyperlink target boundary helpers."""

from __future__ import annotations

from urllib.parse import urlsplit

from svg2ooxml.common.security_boundaries import (
    has_control_character,
    is_blocked_external_host,
)

_ALLOWED_EXTERNAL_HYPERLINK_SCHEMES = {"http", "https", "mailto", "tel"}


def sanitize_external_hyperlink_target(href: str | None) -> str | None:
    """Return a safe external hyperlink target, or ``None`` if unsupported."""

    if not isinstance(href, str):
        return None
    target = href.strip()
    if not target or "\\" in target or has_control_character(target):
        return None

    try:
        parsed = urlsplit(target)
    except ValueError:
        return None

    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_EXTERNAL_HYPERLINK_SCHEMES:
        return None

    if scheme in {"http", "https"}:
        if not parsed.netloc or not parsed.hostname:
            return None
        if is_blocked_external_host(parsed.hostname):
            return None
    elif parsed.netloc:
        return None

    return target


__all__ = ["sanitize_external_hyperlink_target"]
