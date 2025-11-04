"""Marker XML utilities for DrawingML generation."""

from __future__ import annotations

from typing import Mapping

from svg2ooxml.drawingml.xml_builder import a_elem, to_string

__all__ = ["marker_end_elements"]


def marker_end_elements(markers: Mapping[str, str]) -> tuple[str, str]:
    """Return DrawingML marker XML fragments for stroke ends.

    Uses safe lxml-based builders instead of string concatenation.

    Args:
        markers: Mapping of marker positions ("start", "end") to marker types

    Returns:
        Tuple of (head_xml, tail_xml) marker XML strings
    """
    if not markers:
        return "", ""

    head_xml = ""
    tail_xml = ""

    if markers.get("end"):
        head_xml = to_string(a_elem("headEnd", type="triangle", w="med", len="med"))
    if markers.get("start"):
        tail_xml = to_string(a_elem("tailEnd", type="triangle", w="med", len="med"))

    return head_xml, tail_xml
