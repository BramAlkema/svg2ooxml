"""Tests for parser reference helpers."""

from lxml import etree

from svg2ooxml.core.parser.references import (
    EXTERNAL_PROTOCOLS,
    collect_namespaces,
    has_external_references,
)


def _make_element(xml: str) -> etree._Element:
    return etree.fromstring(xml)


def test_collect_namespaces_adds_defaults_and_existing() -> None:
    root = _make_element(
        "<svg xmlns='http://www.w3.org/2000/svg' xmlns:foo='http://example.com/foo'/>"
    )

    namespaces = collect_namespaces(root)

    assert namespaces[None] == "http://www.w3.org/2000/svg"
    assert namespaces["xlink"] == "http://www.w3.org/1999/xlink"
    assert namespaces["foo"] == "http://example.com/foo"


def test_has_external_references_detects_href_protocols() -> None:
    for proto in EXTERNAL_PROTOCOLS:
        svg = f"<svg><image href='{proto}image.png'/></svg>"
        root = _make_element(svg)

        assert has_external_references(root) is True


def test_has_external_references_detects_uppercase_href_protocol() -> None:
    root = _make_element("<svg><image href='HTTPS://example.com/image.png'/></svg>")

    assert has_external_references(root) is True


def test_has_external_references_detects_unsupported_uri_schemes() -> None:
    root = _make_element("<svg><a href='javascript:alert(1)'/></svg>")

    assert has_external_references(root) is True


def test_has_external_references_ignores_local_fragments_and_data_uris() -> None:
    root = _make_element(
        "<svg><use href='#symbol'/><image href='data:image/png;base64,AA=='/></svg>"
    )

    assert has_external_references(root) is False


def test_has_external_references_detects_external_style_attribute_url() -> None:
    root = _make_element(
        "<svg><rect style=\"fill:url('file:///tmp/pattern.png')\"/></svg>"
    )

    assert has_external_references(root) is True


def test_has_external_references_detects_style_urls() -> None:
    root = _make_element("<svg><style>@import url('https://example');</style></svg>")

    assert has_external_references(root) is True


def test_has_external_references_detects_font_family_urls() -> None:
    root = _make_element("<svg><text font-family=\"url('font.woff')\">Hi</text></svg>")

    assert has_external_references(root) is True


def test_has_external_references_returns_false_when_clean() -> None:
    root = _make_element("<svg><rect width='10' height='10'/></svg>")

    assert has_external_references(root) is False
