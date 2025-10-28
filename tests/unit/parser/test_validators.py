"""Tests for parser validators."""

import pytest
from lxml import etree

from svg2ooxml.core.parser.validators import (
    ensure_namespaces,
   ensure_svg_root,
   has_basic_dimensions,
)


def _make_element(xml: str) -> etree._Element:
    return etree.fromstring(xml)


def test_ensure_svg_root_accepts_svg() -> None:
    root = _make_element("<svg xmlns='http://www.w3.org/2000/svg'/>")

    ensure_svg_root(root)  # Should not raise


def test_ensure_svg_root_rejects_non_svg() -> None:
    root = _make_element("<g/>")

    with pytest.raises(ValueError):
        ensure_svg_root(root)


def test_has_basic_dimensions_accepts_viewbox_only() -> None:
    root = _make_element("<svg viewBox='0 0 100 100'/>")

    assert has_basic_dimensions(root) is True


def test_has_basic_dimensions_rejects_missing_sizes() -> None:
    root = _make_element("<svg/>")

    assert has_basic_dimensions(root) is False


def test_ensure_namespaces_adds_defaults() -> None:
    root = _make_element("<svg/>")

    namespaces = ensure_namespaces(root)

    assert namespaces[None] == "http://www.w3.org/2000/svg"
    assert namespaces["xlink"] == "http://www.w3.org/1999/xlink"
