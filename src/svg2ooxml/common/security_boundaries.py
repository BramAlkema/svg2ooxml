"""Shared URL and text security predicates for boundary checks."""

from __future__ import annotations

import ipaddress

_SSRF_HOST_TOKENS = ("metadata.google", "metadata.azure")


def has_control_character(value: str) -> bool:
    """Return whether *value* contains an ASCII control character."""

    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def is_blocked_external_host(hostname: str) -> bool:
    """Return whether a URL host is unsafe for emitted external relationships."""

    host = hostname.strip("[]").rstrip(".").lower()
    if not host:
        return True
    if host == "localhost" or host.endswith(".localhost"):
        return True
    if any(token in host for token in _SSRF_HOST_TOKENS):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_private
        or address.is_reserved
        or address.is_unspecified
    )


__all__ = ["has_control_character", "is_blocked_external_host"]
