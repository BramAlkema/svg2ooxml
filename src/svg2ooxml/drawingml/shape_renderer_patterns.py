"""Pattern tile media registration for DrawingML shape rendering."""

from __future__ import annotations

from dataclasses import replace

from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.paint import PatternPaint
from svg2ooxml.ir.scene import Image


class ShapeRendererPatternMixin:
    """Register pattern tile images and return updated immutable elements."""

    def _register_pattern_tile(self, element):
        """Register pattern tile images as media and update relationship IDs."""
        fill = getattr(element, "fill", None)
        stroke = getattr(element, "stroke", None)
        updated_fill = None
        updated_stroke = None

        if (
            isinstance(fill, PatternPaint)
            and fill.tile_image
            and not fill.tile_relationship_id
        ):
            rid = self._register_tile_image(fill.tile_image)
            if rid:
                updated_fill = replace(fill, tile_relationship_id=rid)

        if stroke is not None:
            paint = getattr(stroke, "paint", None)
            if (
                isinstance(paint, PatternPaint)
                and paint.tile_image
                and not paint.tile_relationship_id
            ):
                rid = self._register_tile_image(paint.tile_image)
                if rid:
                    updated_stroke = replace(
                        stroke,
                        paint=replace(paint, tile_relationship_id=rid),
                    )

        if updated_fill is None and updated_stroke is None:
            return element

        try:
            kwargs = {}
            if updated_fill is not None:
                kwargs["fill"] = updated_fill
            if updated_stroke is not None:
                kwargs["stroke"] = updated_stroke
            return replace(element, **kwargs)
        except TypeError:
            return element

    def _register_tile_image(self, image_data: bytes) -> str | None:
        """Register tile image bytes as media and return relationship ID."""
        try:
            image = Image(
                origin=Point(0.0, 0.0),
                size=Rect(0.0, 0.0, 1.0, 1.0),
                data=image_data,
                format="png",
                metadata={"image_source": "pattern_tile"},
            )
            return self._register_media(image)
        except Exception:
            self._logger.debug("Failed to register pattern tile image", exc_info=True)
            return None


__all__ = ["ShapeRendererPatternMixin"]
