"""Optional runtime dependencies for raster adapter helpers."""

from __future__ import annotations

_DEFAULT_PLACEHOLDER_SIZE = (64, 64)


def adapter_skia():
    from svg2ooxml.drawingml import raster_adapter

    return raster_adapter.skia


__all__ = ["_DEFAULT_PLACEHOLDER_SIZE", "adapter_skia"]
