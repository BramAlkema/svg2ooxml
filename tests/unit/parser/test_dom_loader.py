"""Tests for the parser DOM loader utilities."""

from lxml import etree

from svg2ooxml.parser.dom_loader import ParserOptions, XMLParser, load_dom


def test_load_dom_parses_valid_svg() -> None:
    svg = "<svg><rect/></svg>"

    root = load_dom(svg)

    assert root.tag == "svg"
    assert list(root)[0].tag == "rect"


def test_xml_parser_respects_remove_comments_option() -> None:
    svg = "<svg><!-- comment --><rect/></svg>"
    parser = XMLParser(ParserOptions(remove_comments=True))

    root = parser.parse(svg)

    # lxml strips comments entirely when remove_comments=True
    assert len(root) == 1
    assert root[0].tag == "rect"


def test_validate_root_raises_for_non_svg() -> None:
    parser = XMLParser()
    element = etree.fromstring("<root/>")

    try:
        parser.validate_root(element)
    except ValueError as exc:
        assert "<svg>" in str(exc)
    else:
        raise AssertionError("validate_root should have raised")
