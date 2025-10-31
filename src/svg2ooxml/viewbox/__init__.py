
"""Public viewBox helpers backed by the core traversal module."""

from __future__ import annotations

from .core import (
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
]
