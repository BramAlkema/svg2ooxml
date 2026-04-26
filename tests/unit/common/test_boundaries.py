from __future__ import annotations

import gzip

import pytest

from svg2ooxml.common.boundaries import (
    BoundaryError,
    classify_resource_href,
    decode_data_uri,
    decompress_svgz_bytes,
    is_external_resource_href,
    normalize_remote_resource_url,
    parse_xml_text,
    resolve_local_resource_path,
    sanitize_external_hyperlink_target,
    sanitize_package_filename,
)


def test_safe_xml_parser_clamps_entity_resolution(tmp_path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("XXE_PROBE_CONTENT", encoding="utf-8")
    svg = (
        f'<!DOCTYPE svg [ <!ENTITY xxe SYSTEM "{secret.as_uri()}"> ]>'
        "<svg><text>&xxe;</text></svg>"
    )

    root = parse_xml_text(
        svg,
        recover=True,
        resolve_entities=True,
        load_dtd=True,
        no_network=False,
        huge_tree=True,
    )

    assert "XXE_PROBE_CONTENT" not in "".join(root.itertext())


def test_svgz_decompression_has_output_limit() -> None:
    payload = gzip.compress(b"<svg>" + (b"x" * 64) + b"</svg>")

    with pytest.raises(BoundaryError):
        decompress_svgz_bytes(payload, max_output_bytes=32)


def test_local_resource_resolution_stays_inside_asset_root(tmp_path) -> None:
    asset_root = tmp_path / "assets"
    nested = asset_root / "nested"
    nested.mkdir(parents=True)
    image = nested / "pixel.png"
    image.write_bytes(b"png")
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"secret")

    assert resolve_local_resource_path("nested/pixel.png", asset_root) == image
    assert resolve_local_resource_path("../secret.png", asset_root) is None
    assert resolve_local_resource_path(str(outside), asset_root) is None
    assert resolve_local_resource_path("data:image/png;base64,AA==", asset_root) is None
    assert resolve_local_resource_path("https://example.com/pixel.png", asset_root) is None
    assert resolve_local_resource_path("#symbol", asset_root) is None


def test_resource_reference_classifier_separates_reference_kinds() -> None:
    assert classify_resource_href("url('#clip')").kind == "fragment"
    assert classify_resource_href("data:text/plain,hi").kind == "data"
    assert classify_resource_href("https://example.com/a.png").kind == "remote"
    assert classify_resource_href("file:///tmp/a.png").kind == "file-uri"
    assert classify_resource_href("javascript:alert(1)").kind == "external"

    local = classify_resource_href("icons/pixel%20one.png#view")
    assert local is not None
    assert local.kind == "local-path"
    assert local.path == "icons/pixel one.png"
    assert local.fragment == "view"

    windows_path = classify_resource_href("C:/fonts/Blocky.ttf")
    assert windows_path is not None
    assert windows_path.kind == "local-path"
    assert windows_path.path == "C:/fonts/Blocky.ttf"


def test_external_resource_boundary_blocks_non_local_resolution_targets() -> None:
    assert is_external_resource_href("#symbol") is True
    assert is_external_resource_href("https://example.com/image.png") is True
    assert is_external_resource_href("file:///tmp/image.png") is True
    assert is_external_resource_href("javascript:alert(1)") is True
    assert is_external_resource_href("data:text/plain,hi") is False
    assert is_external_resource_href("images/pixel.png") is False


def test_remote_resource_normalizer_blocks_private_fetch_targets() -> None:
    assert normalize_remote_resource_url("https://example.com/font.woff2") == (
        "https://example.com/font.woff2"
    )
    assert normalize_remote_resource_url("ftp://example.com/font.woff2") is None
    assert normalize_remote_resource_url("http://localhost/font.woff2") is None
    assert normalize_remote_resource_url("http://127.0.0.1/font.woff2") is None
    assert normalize_remote_resource_url("file:///tmp/font.woff2") is None


def test_data_uri_decoding_is_strict_and_bounded() -> None:
    decoded = decode_data_uri("data:text/plain;base64,aGk=")

    assert decoded is not None
    assert decoded.mime_type == "text/plain"
    assert decoded.data == b"hi"
    assert decode_data_uri("data:text/plain;base64,NOT_VALID_BASE64!!!") is None
    assert decode_data_uri("data:text/plain;base64,aGk=", max_bytes=1) is None


def test_external_hyperlink_boundary_blocks_local_network_targets() -> None:
    assert sanitize_external_hyperlink_target("https://example.com/docs") == (
        "https://example.com/docs"
    )
    assert sanitize_external_hyperlink_target("http://localhost/status") is None
    assert sanitize_external_hyperlink_target("http://127.0.0.1/status") is None
    assert sanitize_external_hyperlink_target("http://192.168.1.1/status") is None
    assert sanitize_external_hyperlink_target("http://10.0.0.1/status") is None
    assert sanitize_external_hyperlink_target("http://169.254.169.254/latest") is None


def test_package_filename_sanitizer_drops_path_components() -> None:
    assert sanitize_package_filename("../../evil file.png") == "evil_file.png"
    assert sanitize_package_filename("..", fallback_stem="media") == "media.bin"
