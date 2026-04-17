"""Raster / placeholder fallback filter rendering."""

from __future__ import annotations

import logging

from lxml import etree

from svg2ooxml.drawingml.raster_adapter import RasterAdapter
from svg2ooxml.filters.base import FilterContext, FilterResult


def rasterize_filter(
    element: etree._Element,
    context: FilterContext,
    filter_id: str,
    *,
    raster_adapter: RasterAdapter,
    logger: logging.Logger,
) -> FilterResult | None:
    """Run the raster adapter, falling back to a placeholder on failure."""
    try:
        raster = raster_adapter.render_filter(
            filter_id=filter_id,
            filter_element=element,
            context=context,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Raster adapter failed for %s: %s", filter_id, exc)
        raster = None

    if raster is None:
        placeholder = raster_adapter.generate_placeholder(
            metadata={"renderer": "placeholder", "filter_id": filter_id}
        )
        asset = {
            "type": "raster",
            "format": "png",
            "data": placeholder.image_bytes,
            "relationship_id": placeholder.relationship_id,
            "width_px": placeholder.width_px,
            "height_px": placeholder.height_px,
        }
        metadata = dict(placeholder.metadata)
        metadata.setdefault("fallback_assets", []).append(asset)
        drawingml = f"<!-- svg2ooxml:raster placeholder rel={placeholder.relationship_id} filter={filter_id} -->"
        return FilterResult(
            success=True,
            drawingml=drawingml,
            fallback="bitmap",
            metadata=metadata,
            warnings=["Raster fallback placeholder used"],
        )

    asset = {
        "type": "raster",
        "format": "png",
        "data": raster.image_bytes,
        "relationship_id": raster.relationship_id,
        "width_px": raster.width_px,
        "height_px": raster.height_px,
    }
    metadata = dict(raster.metadata)
    metadata.setdefault("fallback_assets", []).append(asset)
    drawingml = f"<!-- svg2ooxml:raster rel={raster.relationship_id} filter={filter_id} -->"
    return FilterResult(
        success=True,
        drawingml=drawingml,
        fallback="bitmap",
        metadata=metadata,
    )
