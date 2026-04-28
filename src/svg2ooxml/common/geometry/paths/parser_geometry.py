"""Geometry helpers for SVG path parsing."""

from __future__ import annotations

from svg2ooxml.ir.geometry import Point


def _resolve_relative_point(base: Point, x: float, y: float, is_relative: bool) -> Point:
    return Point(base.x + x, base.y + y) if is_relative else Point(x, y)


__all__ = ["_resolve_relative_point"]
