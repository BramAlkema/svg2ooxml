"""Shared helpers for data crossing parser, package, and URL boundaries."""

from __future__ import annotations

from svg2ooxml.common.boundary_types import (
    DATA_URI_RE,
    DEFAULT_MAX_DATA_URI_BYTES,
    DEFAULT_MAX_XML_BYTES,
    EXTERNAL_RESOURCE_SCHEMES,
    REMOTE_FETCH_SCHEMES,
    REMOTE_RESOURCE_SCHEMES,
    BoundaryError,
    DecodedDataUri,
    ResourceReference,
    ResourceReferenceKind,
)
from svg2ooxml.common.hyperlink_boundaries import sanitize_external_hyperlink_target
from svg2ooxml.common.package_boundaries import (
    is_safe_relationship_id,
    next_relationship_id,
    normalize_package_suffix,
    resolve_package_child,
    sanitize_package_filename,
)
from svg2ooxml.common.resource_boundaries import (
    classify_resource_href,
    decode_data_uri,
    is_external_resource_href,
    normalize_remote_resource_url,
    normalize_resource_href,
    path_is_within,
    resolve_local_resource_path,
)
from svg2ooxml.common.security_boundaries import (
    has_control_character,
    is_blocked_external_host,
)
from svg2ooxml.common.xml_boundaries import (
    decompress_svgz_bytes,
    ensure_byte_limit,
    has_forbidden_xml_markers,
    parse_wrapped_xml_fragment,
    parse_xml_bytes,
    parse_xml_text,
    safe_lxml_parser,
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
