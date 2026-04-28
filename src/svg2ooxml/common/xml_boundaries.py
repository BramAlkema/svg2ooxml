"""XML and gzip payload boundary helpers."""

from __future__ import annotations

import gzip
import html
import re
from io import BytesIO

from lxml import etree

from svg2ooxml.common.boundary_types import (
    DEFAULT_MAX_XML_BYTES,
    BoundaryError,
)

_XML_FRAGMENT_WRAPPER_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_.-]*\Z")
_XML_NAMESPACE_PREFIX_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_.-]*\Z")
_FORBIDDEN_XML_MARKERS = ("<!doctype", "<!entity", "<!notation", "<?xml")


class _BlockedExternalResolver(etree.Resolver):
    """Prevent XML external entities from reading files or network resources."""

    def resolve(self, system_url, public_id, context):  # noqa: ANN001, D102
        return self.resolve_string("", context)


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
        ns_decls.append(f'xmlns:{prefix}="{html.escape(str(uri), quote=True)}"')
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


__all__ = [
    "decompress_svgz_bytes",
    "ensure_byte_limit",
    "has_forbidden_xml_markers",
    "parse_wrapped_xml_fragment",
    "parse_xml_bytes",
    "parse_xml_text",
    "safe_lxml_parser",
]
