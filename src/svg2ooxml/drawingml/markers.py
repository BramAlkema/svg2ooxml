"""Marker XML utilities for DrawingML generation."""

from __future__ import annotations

from typing import Mapping

__all__ = ["marker_end_elements"]


def marker_end_elements(markers: Mapping[str, str]) -> tuple[str, str]:
    """Return DrawingML marker XML fragments for stroke ends."""

    if not markers:
        return "", ""

    head_xml = ""
    tail_xml = ""

    if markers.get("end"):
        head_xml = '<a:headEnd type="triangle" w="med" len="med"/>'
    if markers.get("start"):
        tail_xml = '<a:tailEnd type="triangle" w="med" len="med"/>'

    return head_xml, tail_xml
