"""PowerPoint preset pattern mapping."""

from __future__ import annotations

from typing import Any

from lxml import etree as ET

from ._helpers import (
    flatten_pattern_children,
    has_visible_paint,
    is_dot_like_path,
    local_name,
    parse_float_attr,
)


def find_preset_candidate(
    pattern_type: Any,
    element: ET.Element,
    geometry: Any,
    PatternType: type,
) -> str | None:
    """Find PowerPoint preset candidate for pattern."""
    if pattern_type == PatternType.DOTS:
        density = _estimate_dot_density(element, geometry)
        return _map_density_to_preset(density)

    elif pattern_type == PatternType.LINES:
        orientation = _determine_line_orientation(element)
        return _map_orientation_to_preset(orientation)

    elif pattern_type == PatternType.DIAGONAL:
        direction = _determine_diagonal_direction(element)
        return _map_diagonal_to_preset(direction)

    elif pattern_type in [PatternType.GRID, PatternType.CROSS]:
        return "cross"

    return None


def _estimate_dot_density(element: ET.Element, geometry: Any) -> float:
    """Estimate dot density for percentage pattern mapping."""
    children = flatten_pattern_children(element)
    dot_count = sum(
        1
        for child in children
        if has_visible_paint(child)
        and (
            local_name(child.tag) in {"circle", "ellipse"}
            or is_dot_like_path(child)
        )
    )

    # Estimate coverage based on tile size and dot count
    geometry.tile_width * geometry.tile_height
    estimated_coverage = min(dot_count * 0.1, 0.9)  # Simplified estimation

    return estimated_coverage


def _map_density_to_preset(density: float) -> str:
    """Map density to PowerPoint percentage preset."""
    if density <= 0.05:
        return "pct5"
    elif density <= 0.15:
        return "pct10"
    elif density <= 0.22:
        return "pct20"
    elif density <= 0.35:
        return "pct30"
    elif density <= 0.45:
        return "pct40"
    elif density <= 0.55:
        return "pct50"
    else:
        return "pct75"


def _determine_line_orientation(element: ET.Element) -> str:
    """Determine line orientation from pattern content."""
    children = flatten_pattern_children(element)

    for child in children:
        if local_name(child.tag) == "line":
            x1 = parse_float_attr(child, "x1", axis="x", default=0.0)
            y1 = parse_float_attr(child, "y1", axis="y", default=0.0)
            x2 = parse_float_attr(child, "x2", axis="x", default=1.0)
            y2 = parse_float_attr(child, "y2", axis="y", default=0.0)
            if x1 is None or y1 is None or x2 is None or y2 is None:
                continue

            dx = abs(x2 - x1)
            dy = abs(y2 - y1)

            if dx > dy * 3:
                return "horizontal"
            elif dy > dx * 3:
                return "vertical"

    return "horizontal"  # Default


def _map_orientation_to_preset(orientation: str) -> str:
    """Map line orientation to PowerPoint preset."""
    if orientation == "horizontal":
        return "horz"
    elif orientation == "vertical":
        return "vert"
    else:
        return "horz"


def _determine_diagonal_direction(element: ET.Element) -> str:
    """Determine diagonal direction from pattern content."""
    return "down"  # Default to down diagonal


def _map_diagonal_to_preset(direction: str) -> str:
    """Map diagonal direction to PowerPoint preset."""
    if direction == "up":
        return "upDiag"
    else:
        return "dnDiag"
