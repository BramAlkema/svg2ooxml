"""Shared OOXML relationship ID helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable

_REL_ID_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_.-]*\Z")
_REL_ID_PREFIX_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_.-]*\Z")


def is_safe_relationship_id(
    value: object,
    *,
    reserved_ids: Iterable[str] = (),
) -> bool:
    """Return whether *value* is a simple XML-safe relationship ID."""

    return (
        isinstance(value, str)
        and bool(_REL_ID_RE.fullmatch(value))
        and value not in reserved_ids
    )


def next_relationship_id(
    existing_ids: Iterable[object],
    *,
    prefix: str = "rId",
    start: int = 1,
) -> str:
    """Return the next available safe relationship ID for *prefix*."""

    safe_prefix = prefix if _REL_ID_PREFIX_RE.fullmatch(prefix) else "rId"
    used = {value for value in existing_ids if isinstance(value, str)}
    index = max(1, start)
    while True:
        candidate = f"{safe_prefix}{index}"
        if candidate not in used and is_safe_relationship_id(candidate):
            return candidate
        index += 1


__all__ = ["is_safe_relationship_id", "next_relationship_id"]
