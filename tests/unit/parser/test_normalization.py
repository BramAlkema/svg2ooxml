"""Tests for SafeSVGNormalizer."""

from lxml import etree

from svg2ooxml.parser.normalization import NormalizationSettings, SafeSVGNormalizer


def test_normalizer_removes_comments_and_whitespace() -> None:
    normalizer = SafeSVGNormalizer()
    svg = etree.fromstring("<svg><!--c--><g>  <text> hi </text> </g></svg>")

    root, changes = normalizer.normalize(svg)

    assert not any(isinstance(node, etree._Comment) for node in root.iter())
    assert changes["whitespace_normalized"] is True
    assert any(
        entry.get("action") == "normalize_whitespace" for entry in changes["log"]
    )


def test_normalizer_adds_missing_attributes() -> None:
    normalizer = SafeSVGNormalizer(
        NormalizationSettings(fix_namespaces=True, add_missing_attributes=True)
    )
    svg = etree.fromstring("<svg xmlns='http://www.w3.org/2000/svg'/>")

    root, changes = normalizer.normalize(svg)

    assert root.get("version") == "1.1"
    assert "version" in changes["attributes_added"]


def test_normalizer_keeps_containers_with_meaningful_attributes() -> None:
    normalizer = SafeSVGNormalizer()
    svg = etree.fromstring(
        "<svg><g id='keep' style='display:none'></g><g></g></svg>"
    )

    root, changes = normalizer.normalize(svg)

    ids = {
        elem.get("id")
        for elem in root.findall(".//{http://www.w3.org/2000/svg}g")
        if elem.get("id")
    }
    assert "keep" in ids
    assert "g" in changes["structure_fixes"]


def test_normalizer_replaces_control_characters() -> None:
    normalizer = SafeSVGNormalizer()
    svg = etree.Element("svg")
    text = etree.SubElement(svg, "text")
    text.text = "\ufeff spaced"

    root, changes = normalizer.normalize(svg)

    found = root.find(".//{http://www.w3.org/2000/svg}text")
    assert found is not None
    assert "\ufeff" not in found.text
    assert changes["encoding_fixes"]
    assert any(
        entry.get("action") == "fix_encoding" for entry in changes["log"]
    )
