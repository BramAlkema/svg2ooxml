"""Gradient paint resolution facade."""

from __future__ import annotations

from svg2ooxml.core.styling.paint.gradient_builder import build_gradient_paint
from svg2ooxml.core.styling.paint.gradient_metadata import (
    get_gradient_processor,
    record_gradient_metadata,
    record_mesh_gradient_metadata,
)
from svg2ooxml.core.styling.paint.gradient_resolution import (
    collect_gradient_stops,
    gradient_attr,
    parse_stops,
    resolve_gradient_length,
    resolve_gradient_point,
)

__all__ = [
    "build_gradient_paint",
    "collect_gradient_stops",
    "get_gradient_processor",
    "gradient_attr",
    "parse_stops",
    "record_gradient_metadata",
    "record_mesh_gradient_metadata",
    "resolve_gradient_length",
    "resolve_gradient_point",
]
