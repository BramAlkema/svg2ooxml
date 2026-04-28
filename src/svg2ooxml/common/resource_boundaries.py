"""SVG/CSS resource reference boundary helpers."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import unquote, unquote_to_bytes, urlsplit

from svg2ooxml.common.boundary_types import (
    DATA_URI_RE,
    DEFAULT_MAX_DATA_URI_BYTES,
    REMOTE_FETCH_SCHEMES,
    REMOTE_RESOURCE_SCHEMES,
    DecodedDataUri,
    ResourceReference,
)
from svg2ooxml.common.security_boundaries import is_blocked_external_host


def normalize_resource_href(href: str | None) -> str | None:
    """Normalize common SVG/CSS href wrappers for resource resolution."""

    if href is None:
        return None
    token = href.strip()
    if token.lower().startswith("url(") and token.endswith(")"):
        token = token[4:-1].strip()
        if (token.startswith("'") and token.endswith("'")) or (
            token.startswith('"') and token.endswith('"')
        ):
            token = token[1:-1]
    token = token.strip()
    return token or None


def classify_resource_href(href: str | None) -> ResourceReference | None:
    """Classify an SVG/CSS resource reference without resolving it."""

    token = normalize_resource_href(href)
    if not token:
        return None

    lowered = token.lower()
    if lowered.startswith("data:"):
        return ResourceReference(
            raw=href or "",
            normalized=token,
            kind="data",
            scheme="data",
        )
    if token.startswith("#"):
        return ResourceReference(
            raw=href or "",
            normalized=token,
            kind="fragment",
            fragment=token[1:] or None,
        )

    try:
        parsed = urlsplit(token)
    except ValueError:
        return ResourceReference(raw=href or "", normalized=token, kind="external")

    scheme = parsed.scheme.lower()
    if parsed.netloc and not scheme:
        return ResourceReference(raw=href or "", normalized=token, kind="external")
    if scheme in REMOTE_RESOURCE_SCHEMES:
        return ResourceReference(
            raw=href or "",
            normalized=token,
            kind="remote",
            scheme=scheme,
            path=parsed.path or None,
            fragment=parsed.fragment or None,
        )
    if scheme == "file":
        return ResourceReference(
            raw=href or "",
            normalized=token,
            kind="file-uri",
            scheme=scheme,
            path=parsed.path or None,
            fragment=parsed.fragment or None,
        )
    is_windows_drive = _looks_like_windows_drive_path(token, scheme)
    if scheme and not is_windows_drive:
        return ResourceReference(
            raw=href or "",
            normalized=token,
            kind="external",
            scheme=scheme,
            path=parsed.path or None,
            fragment=parsed.fragment or None,
        )

    path = token if is_windows_drive else parsed.path if parsed.path else token
    return ResourceReference(
        raw=href or "",
        normalized=token,
        kind="local-path",
        path=unquote(path),
        fragment=parsed.fragment or None,
    )


def normalize_remote_resource_url(
    href: str | None,
    *,
    allowed_schemes: Iterable[str] = REMOTE_FETCH_SCHEMES,
    block_private_hosts: bool = True,
) -> str | None:
    """Return a safe remote URL for network fetches, or ``None``."""

    reference = classify_resource_href(href)
    if reference is None or reference.kind != "remote":
        return None
    allowed = {scheme.lower() for scheme in allowed_schemes}
    if allowed and (reference.scheme or "") not in allowed:
        return None

    try:
        parsed = urlsplit(reference.normalized)
    except ValueError:
        return None
    if not parsed.netloc or not parsed.hostname:
        return None
    if block_private_hosts and is_blocked_external_host(parsed.hostname):
        return None
    return reference.normalized


def is_external_resource_href(href: str | None) -> bool:
    """Return true for hrefs that must not be resolved from local disk."""

    reference = classify_resource_href(href)
    return bool(reference and reference.is_external_for_local_resolution)


def decode_data_uri(
    href: str | None,
    *,
    max_bytes: int = DEFAULT_MAX_DATA_URI_BYTES,
) -> DecodedDataUri | None:
    """Decode a data URI with strict base64 and output-size checks."""

    reference = classify_resource_href(href)
    if reference is None or reference.kind != "data":
        return None
    match = DATA_URI_RE.match(reference.normalized)
    if not match:
        return None

    mime_type = (match.group("mime") or "").strip() or None
    params = match.group("params") or ""
    payload = match.group("payload")
    is_base64 = any(
        part.strip().lower() == "base64"
        for part in params.split(";")
        if part.strip()
    )
    if is_base64:
        try:
            data = base64.b64decode(payload.strip(), validate=True)
        except (ValueError, binascii.Error):
            return None
    else:
        data = unquote_to_bytes(payload)

    if max_bytes >= 0 and len(data) > max_bytes:
        return None
    return DecodedDataUri(data=data, mime_type=mime_type)


def resolve_local_resource_path(
    href: str | None,
    base_dir: Path | str,
    *,
    asset_root: Path | str | None = None,
) -> Path | None:
    """Resolve a local href without allowing absolute or ``..`` escapes."""

    reference = classify_resource_href(href)
    if reference is None or not reference.is_local_path:
        return None

    try:
        base = Path(base_dir).expanduser().resolve()
        root = Path(asset_root).expanduser().resolve() if asset_root else base
        candidate = Path(reference.path or reference.normalized)
        target = (
            candidate.resolve()
            if candidate.is_absolute()
            else (base / candidate).resolve()
        )
    except (OSError, RuntimeError, ValueError):
        return None

    if not path_is_within(target, root):
        return None
    if not target.is_file():
        return None
    return target


def path_is_within(path: Path, root: Path) -> bool:
    """Return whether *path* is inside *root* after resolution."""

    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _looks_like_windows_drive_path(token: str, scheme: str) -> bool:
    return len(scheme) == 1 and len(token) >= 2 and token[1] == ":"


__all__ = [
    "classify_resource_href",
    "decode_data_uri",
    "is_external_resource_href",
    "normalize_remote_resource_url",
    "normalize_resource_href",
    "path_is_within",
    "resolve_local_resource_path",
]
