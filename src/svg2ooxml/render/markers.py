"""Utilities for marker placement along paths."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from svg2ooxml.core.resvg.geometry.primitives import LineTo, MoveTo
from svg2ooxml.core.resvg.usvg_tree import MarkerNode, Tree


@dataclass(slots=True)
class MarkerPlacement:
    marker: MarkerNode
    position: Tuple[float, float]
    angle: float


def resolve_marker(tree: Tree, href: Optional[str]) -> Optional[MarkerNode]:
    if not href:
        return None
    return tree.resolve_marker(href)


def compute_marker_positions(commands: List[object]) -> List[Tuple[float, float, float]]:
    positions: List[Tuple[float, float, float]] = []
    last_point: Optional[Tuple[float, float]] = None
    for item in commands:
        if isinstance(item, MoveTo):
            last_point = (item.x, item.y)
        elif isinstance(item, LineTo):
            if last_point is not None:
                dx = item.x - last_point[0]
                dy = item.y - last_point[1]
                angle = math.atan2(dy, dx) if dx or dy else 0.0
                positions.append((item.x, item.y, angle))
            last_point = (item.x, item.y)
    return positions


__all__ = ["MarkerPlacement", "resolve_marker", "compute_marker_positions"]
