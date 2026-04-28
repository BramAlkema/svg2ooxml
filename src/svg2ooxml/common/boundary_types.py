"""Shared trust-boundary data types and constants."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

DEFAULT_MAX_XML_BYTES = 20 * 1024 * 1024
DEFAULT_MAX_DATA_URI_BYTES = 64 * 1024 * 1024

DATA_URI_RE = re.compile(
    r"^data:(?P<mime>[^;,]*)?(?P<params>(?:;[^,]*)*),(?P<payload>.*)$",
    re.IGNORECASE | re.DOTALL,
)
EXTERNAL_RESOURCE_SCHEMES: tuple[str, ...] = (
    "http://",
    "https://",
    "ftp://",
    "file://",
)
REMOTE_RESOURCE_SCHEMES: frozenset[str] = frozenset({"http", "https", "ftp"})
REMOTE_FETCH_SCHEMES: frozenset[str] = frozenset({"http", "https"})
ResourceReferenceKind = Literal[
    "data",
    "fragment",
    "remote",
    "file-uri",
    "external",
    "local-path",
]


class BoundaryError(ValueError):
    """Raised when input violates a trust-boundary limit."""


@dataclass(frozen=True, slots=True)
class DecodedDataUri:
    """Decoded data URI payload."""

    data: bytes
    mime_type: str | None = None


@dataclass(frozen=True, slots=True)
class ResourceReference:
    """Classified SVG/CSS resource reference after ``url(...)`` normalization."""

    raw: str
    normalized: str
    kind: ResourceReferenceKind
    scheme: str | None = None
    path: str | None = None
    fragment: str | None = None

    @property
    def is_local_path(self) -> bool:
        return self.kind == "local-path"

    @property
    def is_external_for_local_resolution(self) -> bool:
        return self.kind in {"fragment", "remote", "file-uri", "external"}


__all__ = [
    "BoundaryError",
    "DATA_URI_RE",
    "DEFAULT_MAX_DATA_URI_BYTES",
    "DEFAULT_MAX_XML_BYTES",
    "DecodedDataUri",
    "EXTERNAL_RESOURCE_SCHEMES",
    "REMOTE_FETCH_SCHEMES",
    "REMOTE_RESOURCE_SCHEMES",
    "ResourceReference",
    "ResourceReferenceKind",
]
