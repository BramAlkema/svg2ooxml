"""Rasterizer that renders IR elements to PNG using skia-python."""

from __future__ import annotations

import math

from svg2ooxml.drawingml.rasterizer_backend import SKIA_AVAILABLE, skia
from svg2ooxml.drawingml.rasterizer_geometry import RasterizerGeometryMixin
from svg2ooxml.drawingml.rasterizer_paint import RasterizerPaintMixin
from svg2ooxml.drawingml.rasterizer_shapes import RasterizerShapeMixin
from svg2ooxml.drawingml.rasterizer_types import RasterResult
from svg2ooxml.ir.scene import Group, Image
from svg2ooxml.ir.scene import Path as IRPath
from svg2ooxml.ir.shapes import Circle, Ellipse, Rectangle


class Rasterizer(
    RasterizerShapeMixin,
    RasterizerPaintMixin,
    RasterizerGeometryMixin,
):
    """Render IR elements to raster images using skia-python."""

    def __init__(self, *, scale: float = 1.0) -> None:
        if not SKIA_AVAILABLE:  # pragma: no cover - guarded by availability flag
            raise RuntimeError("skia-python is not installed; rasterization unavailable.")
        self._scale = max(0.1, float(scale))

    def rasterize(self, element) -> RasterResult | None:
        if isinstance(element, Group):
            return self._rasterize_group(element)
        if isinstance(element, Image):
            return None

        bounds = self._expanded_bounds(element)
        if bounds.width <= 0 or bounds.height <= 0:
            return None

        width_px = max(int(math.ceil(bounds.width * self._scale)), 1)
        height_px = max(int(math.ceil(bounds.height * self._scale)), 1)

        try:
            # skia-python >= 138 dropped alphaType on the direct width/height
            # overload. ImageInfo keeps the requested RGBA premul explicit.
            info = skia.ImageInfo.Make(
                width_px,
                height_px,
                skia.ColorType.kRGBA_8888_ColorType,
                skia.AlphaType.kPremul_AlphaType,
            )
            surface = skia.Surface(info)
        except (AttributeError, TypeError):  # pragma: no cover - compatibility fallback
            surface = skia.Surface(
                width_px,
                height_px,
                colorType=skia.ColorType.kRGBA_8888_ColorType,
            )
        canvas = surface.getCanvas()
        canvas.clear(skia.ColorTRANSPARENT)
        canvas.scale(self._scale, self._scale)
        canvas.translate(-bounds.x, -bounds.y)

        if not isinstance(element, (Rectangle, Circle, Ellipse, IRPath)):
            return None
        drawn = self._draw_element(canvas, element)

        if not drawn:
            return None

        image = surface.makeImageSnapshot()
        try:
            data = image.encodeToData()
        except TypeError:  # pragma: no cover - legacy signature
            png_format = getattr(getattr(skia, "EncodedImageFormat", skia), "kPNG", None)
            if png_format is None:
                png_format = getattr(skia, "kPNG", None)
            quality = 100
            if png_format is None:
                data = image.encodeToData()
            else:
                try:
                    data = image.encodeToData(png_format, quality)
                except TypeError:
                    data = image.encodeToData(png_format)
        if not data:
            return None

        return RasterResult(
            data=bytes(data),
            width_px=width_px,
            height_px=height_px,
            bounds=bounds,
        )

    def _rasterize_group(self, group: Group) -> RasterResult | None:
        """Rasterize a group by drawing all children onto one surface."""
        bounds = self._group_bounds(group)
        if bounds.width <= 0 or bounds.height <= 0:
            return None

        width_px = max(int(math.ceil(bounds.width * self._scale)), 1)
        height_px = max(int(math.ceil(bounds.height * self._scale)), 1)

        try:
            info = skia.ImageInfo.Make(
                width_px,
                height_px,
                skia.ColorType.kRGBA_8888_ColorType,
                skia.AlphaType.kPremul_AlphaType,
            )
            surface = skia.Surface(info)
        except (AttributeError, TypeError):  # pragma: no cover
            surface = skia.Surface(
                width_px,
                height_px,
                colorType=skia.ColorType.kRGBA_8888_ColorType,
            )

        canvas = surface.getCanvas()
        canvas.clear(skia.ColorTRANSPARENT)
        canvas.scale(self._scale, self._scale)
        canvas.translate(-bounds.x, -bounds.y)

        drawn_any = False
        canvas.save()
        try:
            clip_path = self._clip_path(group)
            if clip_path is not None and clip_path.isEmpty():
                return None
            if clip_path is not None:
                canvas.clipPath(clip_path, skia.ClipOp.kIntersect, True)
            for child in group.children:
                if self._draw_element(canvas, child):
                    drawn_any = True
        finally:
            canvas.restore()

        if not drawn_any:
            return None

        image = surface.makeImageSnapshot()
        try:
            data = image.encodeToData()
        except TypeError:  # pragma: no cover
            data = image.encodeToData()
        if not data:
            return None

        return RasterResult(
            data=bytes(data),
            width_px=width_px,
            height_px=height_px,
            bounds=bounds,
        )


__all__ = ["Rasterizer", "RasterResult", "SKIA_AVAILABLE"]
