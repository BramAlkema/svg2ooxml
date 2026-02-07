"""Marker XML utilities for DrawingML generation."""

from __future__ import annotations

from collections.abc import Mapping

from lxml import etree

from svg2ooxml.drawingml.xml_builder import a_elem

__all__ = ["marker_end_elements"]


def marker_end_elements(
    markers: Mapping[str, str],
) -> tuple[etree._Element | None, etree._Element | None]:
    """Return DrawingML marker elements for stroke ends.

    Args:
        markers: Mapping of marker positions ("start", "end") to marker types

    Returns:
        Tuple of (head_elem, tail_elem) — each is an lxml Element or None
    """
    if not markers:
        return None, None

    head_elem = a_elem("headEnd", type="triangle", w="med", len="med") if markers.get("end") else None
    tail_elem = a_elem("tailEnd", type="triangle", w="med", len="med") if markers.get("start") else None

    return head_elem, tail_elem
