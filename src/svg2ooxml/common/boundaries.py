"""Shared helpers for data crossing parser, package, and URL boundaries."""

from __future__ import annotations

import base64
import binascii
import gzip
import html
import ipaddress
import re
from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, unquote_to_bytes, urlsplit

from lxml import etree

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

_REL_ID_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_.-]*\Z")
_REL_ID_PREFIX_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_.-]*\Z")
_SAFE_PACKAGE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_SAFE_PACKAGE_SUFFIX_RE = re.compile(r"\.[A-Za-z0-9]{1,16}\Z")
_XML_FRAGMENT_WRAPPER_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_.-]*\Z")
_XML_NAMESPACE_PREFIX_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_.-]*\Z")
_FORBIDDEN_XML_MARKERS = ("<!doctype", "<!entity", "<!notation", "<?xml")
_ALLOWED_EXTERNAL_HYPERLINK_SCHEMES = {"http", "https", "mailto", "tel"}
_SSRF_HOST_TOKENS = ("metadata.google", "metadata.azure")


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


class _BlockedExternalResolver(etree.Resolver):
    """Prevent XML external entities from reading files or network resources."""

    def resolve(self, system_url, public_id, context):  # noqa: ANN001, D102
        return self.resolve_string("", context)


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


def safe_lxml_parser(
    *,
    remove_comments: bool = False,
    remove_blank_text: bool = False,
    strip_cdata: bool = False,
    recover: bool = False,
    remove_pis: bool = False,
    resolve_entities: object = False,
    load_dtd: object = False,
    no_network: object = True,
    huge_tree: object = False,
) -> etree.XMLParser:
    """Create an lxml XML parser with unsafe switches clamped off.

    Compatibility options are accepted so legacy parser configs can pass their
    existing dictionaries through this helper. Entity resolution, DTD loading,
    network fetches, and huge-tree mode are always disabled.
    """

    del resolve_entities, load_dtd, no_network, huge_tree
    parser = etree.XMLParser(
        remove_comments=remove_comments,
        remove_blank_text=remove_blank_text,
        strip_cdata=strip_cdata,
        recover=recover,
        remove_pis=remove_pis,
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=False,
    )
    parser.resolvers.add(_BlockedExternalResolver())
    return parser


def ensure_byte_limit(
    data: bytes,
    *,
    max_bytes: int = DEFAULT_MAX_XML_BYTES,
    description: str = "payload",
) -> bytes:
    """Return *data* if it is within the configured size limit."""

    if max_bytes >= 0 and len(data) > max_bytes:
        raise BoundaryError(
            f"{description} exceeds {max_bytes} bytes at trust boundary"
        )
    return data


def parse_xml_bytes(
    data: bytes,
    *,
    max_bytes: int = DEFAULT_MAX_XML_BYTES,
    description: str = "XML payload",
    **parser_options: object,
) -> etree._Element:
    """Parse XML bytes using the shared safe parser."""

    bounded = ensure_byte_limit(data, max_bytes=max_bytes, description=description)
    parser = safe_lxml_parser(**parser_options)
    return etree.fromstring(bounded, parser=parser)


def parse_xml_text(
    text: str,
    *,
    max_bytes: int = DEFAULT_MAX_XML_BYTES,
    description: str = "XML payload",
    **parser_options: object,
) -> etree._Element:
    """Parse XML text using the shared safe parser."""

    return parse_xml_bytes(
        text.encode("utf-8"),
        max_bytes=max_bytes,
        description=description,
        **parser_options,
    )


def has_forbidden_xml_markers(value: str | None) -> bool:
    """Return true when a fragment contains declarations we never ingest."""

    lowered = (value or "").lower()
    return any(marker in lowered for marker in _FORBIDDEN_XML_MARKERS)


def parse_wrapped_xml_fragment(
    fragment: str,
    *,
    namespaces: dict[str, str] | None = None,
    wrapper: str = "root",
    max_bytes: int = DEFAULT_MAX_XML_BYTES,
    description: str = "XML fragment",
) -> etree._Element:
    """Parse one or more XML elements under a generated wrapper root."""

    if has_forbidden_xml_markers(fragment):
        raise BoundaryError("XML fragment contains forbidden declarations")
    if not _XML_FRAGMENT_WRAPPER_RE.fullmatch(wrapper):
        raise BoundaryError(f"Unsafe XML fragment wrapper name: {wrapper!r}")
    namespaces = namespaces or {}
    ns_decls: list[str] = []
    for prefix, uri in namespaces.items():
        if not _XML_NAMESPACE_PREFIX_RE.fullmatch(prefix):
            raise BoundaryError(f"Unsafe XML namespace prefix: {prefix!r}")
        ns_decls.append(
            f'xmlns:{prefix}="{html.escape(str(uri), quote=True)}"'
        )
    attrs = f" {' '.join(ns_decls)}" if ns_decls else ""
    wrapped = f"<{wrapper}{attrs}>{fragment}</{wrapper}>"
    return parse_xml_text(
        wrapped,
        max_bytes=max_bytes,
        description=description,
        recover=False,
    )


def decompress_svgz_bytes(
    data: bytes,
    *,
    max_input_bytes: int = DEFAULT_MAX_XML_BYTES,
    max_output_bytes: int = DEFAULT_MAX_XML_BYTES,
) -> bytes:
    """Return SVG bytes, inflating gzip input with bounded output size."""

    ensure_byte_limit(data, max_bytes=max_input_bytes, description="compressed SVG")
    if not data.startswith(b"\x1f\x8b"):
        return ensure_byte_limit(
            data,
            max_bytes=max_output_bytes,
            description="SVG XML",
        )

    try:
        with gzip.GzipFile(fileobj=BytesIO(data)) as archive:
            decoded = archive.read(max_output_bytes + 1)
    except (OSError, EOFError) as exc:
        raise BoundaryError("Invalid gzip-compressed SVG payload") from exc

    return ensure_byte_limit(
        decoded,
        max_bytes=max_output_bytes,
        description="decompressed SVG XML",
    )


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
        target = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()
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
    "classify_resource_href",
    "decode_data_uri",
    "decompress_svgz_bytes",
    "ensure_byte_limit",
    "has_control_character",
    "has_forbidden_xml_markers",
    "is_blocked_external_host",
    "is_external_resource_href",
    "is_safe_relationship_id",
    "next_relationship_id",
    "normalize_package_suffix",
    "normalize_remote_resource_url",
    "normalize_resource_href",
    "parse_wrapped_xml_fragment",
    "parse_xml_bytes",
    "parse_xml_text",
    "path_is_within",
    "resolve_local_resource_path",
    "resolve_package_child",
    "safe_lxml_parser",
    "sanitize_external_hyperlink_target",
    "sanitize_package_filename",
]
