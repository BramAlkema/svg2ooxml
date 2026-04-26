"""Helpers for PowerPoint-style motion path strings."""

from __future__ import annotations

import re

from svg2ooxml.ir.geometry import SegmentType

from .parser import parse_path_data

_MOTION_PATH_END_RE = re.compile(r"\s+E\s*$")


def strip_motion_path_end_marker(path_value: str) -> str:
    """Remove the DrawingML ``E`` path terminator before SVG path parsing."""
    return _MOTION_PATH_END_RE.sub("", path_value.strip(), count=1)


def parse_motion_path_data(path_value: str) -> list[SegmentType]:
    """Parse a motion path that may include DrawingML's terminal ``E`` marker."""
    return parse_path_data(strip_motion_path_end_marker(path_value))
