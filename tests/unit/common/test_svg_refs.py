from __future__ import annotations

from svg2ooxml.common.svg_refs import (
    local_name,
    local_url_id,
    namespace_uri,
    reference_id,
    unwrap_url_reference,
)


def test_local_name_strips_xml_namespace() -> None:
    assert local_name("{http://www.w3.org/2000/svg}rect") == "rect"
    assert local_name("linearGradient") == "linearGradient"
    assert local_name(None) == ""


def test_namespace_uri_extracts_elementtree_namespace() -> None:
    assert namespace_uri("{http://www.w3.org/2000/svg}rect") == "http://www.w3.org/2000/svg"
    assert namespace_uri("rect") is None
    assert namespace_uri(None) is None


def test_unwrap_url_reference_preserves_reference_kind() -> None:
    assert unwrap_url_reference("url(#clip)") == "#clip"
    assert unwrap_url_reference("url('image.png')") == "image.png"
    assert unwrap_url_reference("  #mask  ") == "#mask"
    assert unwrap_url_reference("") is None


def test_reference_id_accepts_wrapped_fragment_and_plain_ids() -> None:
    assert reference_id("url(#grad)") == "grad"
    assert reference_id("#grad") == "grad"
    assert reference_id("grad") == "grad"


def test_local_url_id_rejects_non_fragment_references() -> None:
    assert local_url_id("url(#clip)") == "clip"
    assert local_url_id("#clip") == "clip"
    assert local_url_id("clip") is None
    assert local_url_id("url(image.png)") is None
