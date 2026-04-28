"""OPC package path and relationship boundary helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from svg2ooxml.common.boundary_types import BoundaryError

_REL_ID_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_.-]*\Z")
_REL_ID_PREFIX_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_.-]*\Z")
_SAFE_PACKAGE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_SAFE_PACKAGE_SUFFIX_RE = re.compile(r"\.[A-Za-z0-9]{1,16}\Z")


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


def sanitize_package_filename(
    filename: str | None,
    *,
    fallback_stem: str = "part",
    fallback_suffix: str = ".bin",
) -> str:
    """Return a single safe OPC filename with no directory components."""

    raw = str(filename or "").replace("\\", "/").rstrip("/")
    name = raw.rsplit("/", 1)[-1].strip()
    if name in {"", ".", ".."}:
        name = ""

    path = Path(name)
    stem = path.stem if path.stem not in {"", ".", ".."} else ""
    safe_stem = _SAFE_PACKAGE_FILENAME_RE.sub("_", stem).strip("._")
    if not safe_stem:
        safe_stem = fallback_stem
    suffix = normalize_package_suffix(path.suffix, fallback_suffix)
    return f"{safe_stem}{suffix}"


def normalize_package_suffix(suffix: str | None, fallback: str) -> str:
    """Return a safe OPC filename suffix."""

    fallback_suffix = fallback if fallback.startswith(".") else f".{fallback}"
    fallback_suffix = fallback_suffix.lower()
    if not _SAFE_PACKAGE_SUFFIX_RE.fullmatch(fallback_suffix):
        fallback_suffix = ".bin"

    candidate = (suffix or "").strip()
    if candidate and not candidate.startswith("."):
        candidate = f".{candidate}"
    candidate = candidate.lower()
    if _SAFE_PACKAGE_SUFFIX_RE.fullmatch(candidate):
        return candidate
    return fallback_suffix


def resolve_package_child(
    package_root: Path,
    package_path: Path,
    *,
    required_prefix: Path | None = None,
) -> Path:
    """Resolve an OPC child path and reject traversal outside the package root."""

    root = package_root.resolve()
    target = (package_root / package_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise BoundaryError(
            f"Package part escapes PPTX staging directory: {package_path}"
        ) from exc

    if required_prefix is not None:
        prefix = (package_root / required_prefix).resolve()
        try:
            target.relative_to(prefix)
        except ValueError as exc:
            raise BoundaryError(
                f"Package part is outside required prefix {required_prefix}: {package_path}"
            ) from exc

    return target


__all__ = [
    "is_safe_relationship_id",
    "next_relationship_id",
    "normalize_package_suffix",
    "resolve_package_child",
    "sanitize_package_filename",
]
