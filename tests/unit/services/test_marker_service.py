"""Tests for the marker service helper."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.services.marker_service import MarkerService


def _build_marker(markup: str) -> etree._Element:
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg'>"
        f"{markup}"
        "</svg>"
    )
    root = etree.fromstring(svg)
    return root[0]


def test_marker_service_parses_definition() -> None:
    marker_element = _build_marker(
        "<marker id='arrow' refX='1' refY='2' markerWidth='4' markerHeight='5' orient='auto' markerUnits='userSpaceOnUse'>"
        "  <path d='M0,0 L1,0 L0,1 z'/>"
        "</marker>"
    )

    service = MarkerService()
    service.update_definitions({"arrow": marker_element})

    definition = service.get_definition("arrow")
    assert definition is not None
    assert definition.marker_id == "arrow"
    assert definition.ref_x == 1.0
    assert definition.ref_y == 2.0
    assert definition.marker_width == 4.0
    assert definition.marker_height == 5.0
    assert definition.marker_units == "userSpaceOnUse"
    assert definition.preserve_aspect_ratio is None


def test_marker_service_definition_cache_shared() -> None:
    marker_element = _build_marker("<marker id='triangle'><path d='M0,0 L1,0 L0,1 z'/></marker>")

    service = MarkerService()
    service.update_definitions({"triangle": marker_element})

    first = service.get_definition("triangle")
    second = service.get_definition("triangle")
    assert first is not None and second is not None
    assert first is second


def test_marker_service_clone_retains_definitions() -> None:
    marker_element = _build_marker("<marker id='diamond' markerWidth='6' markerHeight='6'><path d='M0,0 L1,1 L0,2 z'/></marker>")

    service = MarkerService()
    service.update_definitions({"diamond": marker_element})
    original = service.get_definition("diamond")

    clone = service.clone()
    cloned_definition = clone.get_definition("diamond")

    assert original is not None and cloned_definition is not None
    assert cloned_definition.marker_id == original.marker_id
    assert cloned_definition is not original
