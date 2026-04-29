"""Shared utility functions used across pattern sub-modules."""

from __future__ import annotations

import math

from lxml import etree as ET

from svg2ooxml.common.style.css_values import parse_style_declarations
from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.common.units.lengths import resolve_length_px
from svg2ooxml.core.styling.style_helpers import parse_percentage


def style_map(element: ET.Element) -> dict[str, str]:
    """Parse an element's inline ``style`` attribute into a dict."""
    return parse_style_declarations(element.get("style"))[0]


def is_visible_paint_token(value: str | None) -> bool:
    """Return True when *value* represents a visible paint specification."""
    if value is None:
        return False
    token = value.strip().lower()
    return bool(token) and token not in {"none", "transparent"}


def has_visible_paint(element: ET.Element) -> bool:
    """Return True when *element* has a visible fill or stroke."""
    sm = style_map(element)
    fill = element.get("fill") or sm.get("fill")
    stroke = element.get("stroke") or sm.get("stroke")
    return is_visible_paint_token(fill) or is_visible_paint_token(stroke)


def has_visible_fill(element: ET.Element) -> bool:
    """Return True when *element* has a visible fill."""
    sm = style_map(element)
    fill = element.get("fill") or sm.get("fill")
    return is_visible_paint_token(fill)


def flatten_pattern_children(element: ET.Element) -> list[ET.Element]:
    """Walk through groups and return leaf shape elements."""
    flattened: list[ET.Element] = []

    def _walk(node: ET.Element) -> None:
        for child in node:
            if not isinstance(child.tag, str):
                continue
            if local_name(child.tag) in {"g", "a", "switch"}:
                _walk(child)
                continue
            flattened.append(child)

    _walk(element)
    return flattened


def is_dot_like_path(element: ET.Element) -> bool:
    """Return True when a ``<path>`` element looks like a dot/arc."""
    if local_name(element.tag) != "path":
        return False
    if not has_visible_fill(element):
        return False

    path_data = (element.get("d") or "").upper()
    if (
        "A" in path_data
        and "L" not in path_data
        and "C" not in path_data
        and "Q" not in path_data
    ):
        return True

    for name, value in element.attrib.items():
        if local_name(name) == "type" and value == "arc":
            return True
    return False


def pattern_opacity(value: str | None, default: float = 1.0) -> float:
    """Parse an opacity value, clamping to [0, 1]."""
    if value is None:
        return default
    try:
        return max(0.0, min(1.0, parse_percentage(value)))
    except Exception:
        return default


def parse_float_attr(
    element: ET.Element,
    attribute: str,
    *,
    axis: str = "x",
    default: float | None = None,
) -> float | None:
    """Parse a numeric SVG length attribute, returning ``default`` on failure."""
    value = element.get(attribute)
    if value is None:
        return default
    parsed = resolve_length_px(value, None, axis=axis, default=math.nan)
    if parsed == parsed:
        return parsed
    return default
