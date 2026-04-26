"""Tests for DrawingML XML fragment ingestion."""

import pytest

from svg2ooxml.drawingml.xml_builder import a_elem, graft_xml_fragment


def test_graft_xml_fragment_rejects_forbidden_declarations() -> None:
    parent = a_elem("effectLst")

    with pytest.raises(ValueError, match="forbidden declarations"):
        graft_xml_fragment(
            parent,
            '<!DOCTYPE x [<!ENTITY ext SYSTEM "file:///etc/passwd">]><a:blur/>',
        )

    assert len(parent) == 0
