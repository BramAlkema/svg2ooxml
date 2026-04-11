"""Helpers for filter fallback asset placement and registration."""

from __future__ import annotations

from collections.abc import Mapping

from svg2ooxml.ir.geometry import Rect


def resolve_filter_fallback_bounds(
    default_bounds: Rect | None,
    metadata: Mapping[str, object] | None,
) -> Rect | None:
    """Return fallback bounds overridden by filter metadata when available."""

    if not isinstance(metadata, Mapping):
        return default_bounds

    bounds_dict = metadata.get("bounds")
    if not isinstance(bounds_dict, Mapping):
        return default_bounds

    base_x = default_bounds.x if default_bounds is not None else 0.0
    base_y = default_bounds.y if default_bounds is not None else 0.0
    base_width = default_bounds.width if default_bounds is not None else 0.0
    base_height = default_bounds.height if default_bounds is not None else 0.0

    try:
        return Rect(
            float(bounds_dict.get("x", base_x)),
            float(bounds_dict.get("y", base_y)),
            float(bounds_dict.get("width", base_width)),
            float(bounds_dict.get("height", base_height)),
        )
    except (TypeError, ValueError):
        return default_bounds


__all__ = ["resolve_filter_fallback_bounds"]
