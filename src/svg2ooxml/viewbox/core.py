"""Compatibility layer exposing the traversal viewbox helpers."""

from svg2ooxml.core.traversal.viewbox import (
    PreserveAspectRatio,
    ViewBox,
    ViewBoxResult,
    Viewport,
    ViewportEngine,
    compute_viewbox,
    parse_preserve_aspect_ratio,
    parse_viewbox_attribute,
    resolve_viewbox,
    resolve_viewbox_dimensions,
    viewbox_matrix_from_element,
)

__all__ = [
    "PreserveAspectRatio",
    "ViewBox",
    "ViewBoxResult",
    "Viewport",
    "ViewportEngine",
    "compute_viewbox",
    "parse_preserve_aspect_ratio",
    "parse_viewbox_attribute",
    "resolve_viewbox",
    "resolve_viewbox_dimensions",
    "viewbox_matrix_from_element",
]
