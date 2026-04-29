"""Rendering helpers mixed into :mod:`svg2ooxml.drawingml.raster_adapter`."""

from __future__ import annotations

from svg2ooxml.drawingml.raster_adapter_pipeline import RasterAdapterPipelineMixin
from svg2ooxml.drawingml.raster_adapter_preview_runtime import (
    RasterAdapterPreviewRuntimeMixin,
)


class RasterAdapterRenderingMixin(
    RasterAdapterPipelineMixin,
    RasterAdapterPreviewRuntimeMixin,
):
    """Optional skia/resvg render paths for ``RasterAdapter``."""


__all__ = ["RasterAdapterRenderingMixin"]
