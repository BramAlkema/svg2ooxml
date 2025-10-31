"""Rasterizer that renders IR elements to PNG using skia-python."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Tuple

from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect, SegmentType
from svg2ooxml.ir.paint import (
    LinearGradientPaint,
    PatternPaint,
    RadialGradientPaint,
    SolidPaint,
    Stroke,
    StrokeCap,
    StrokeJoin,
)
from svg2ooxml.ir.scene import Group, Image, Path as IRPath
from svg2ooxml.ir.shapes import Circle, Ellipse, Rectangle

try:  # pragma: no cover - optional dependency
    import skia

    SKIA_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    skia = None  # type: ignore
    SKIA_AVAILABLE = False

from svg2ooxml.common.geometry.paths.drawingml import compute_path_bounds


@dataclass(frozen=True)
class RasterResult:
    data: bytes
    width_px: int
    height_px: int
    bounds: Rect


class Rasterizer:
    """Render IR elements to raster images using skia-python."""

    def __init__(self, *, scale: float = 1.0) -> None:
        if not SKIA_AVAILABLE:  # pragma: no cover - guarded by availability flag
            raise RuntimeError("skia-python is not installed; rasterization unavailable.")
        self._scale = max(0.1, float(scale))

    def rasterize(self, element) -> RasterResult | None:
        if isinstance(element, Group):
            return None
        if isinstance(element, Image):
            return None

        bounds = self._expanded_bounds(element)
        if bounds.width <= 0 or bounds.height <= 0:
            return None

        width_px = max(int(math.ceil(bounds.width * self._scale)), 1)
        height_px = max(int(math.ceil(bounds.height * self._scale)), 1)

        try:
            # skia-python ≥ 138 dropped the alphaType argument on the direct width/height
            # overload. Build an ImageInfo so that we always request RGBA premul explicitly.
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

        drawn = False
        if isinstance(element, Rectangle):
            drawn = self._draw_rectangle(canvas, element)
        elif isinstance(element, Circle):
            drawn = self._draw_circle(canvas, element)
        elif isinstance(element, Ellipse):
            drawn = self._draw_ellipse(canvas, element)
        elif isinstance(element, IRPath):
            drawn = self._draw_path(canvas, element)
        else:
            return None

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

    # ------------------------------------------------------------------ #
    # Drawing helpers
    # ------------------------------------------------------------------ #

    def _draw_rectangle(self, canvas: "skia.Canvas", rect: Rectangle) -> bool:
        sk_rect = skia.Rect.MakeXYWH(rect.bounds.x, rect.bounds.y, rect.bounds.width, rect.bounds.height)
        drawn = False
        if isinstance(rect.fill, SolidPaint):
            paint = self._paint_from_solid(rect.fill)
            if paint:
                canvas.drawRect(sk_rect, paint)
                drawn = True
        if rect.stroke and isinstance(rect.stroke.paint, SolidPaint):
            paint = self._paint_from_stroke(rect.stroke)
            if paint:
                canvas.drawRect(sk_rect, paint)
                drawn = True
        return drawn

    def _draw_circle(self, canvas: "skia.Canvas", circle: Circle) -> bool:
        rect = skia.Rect.MakeXYWH(
            circle.center.x - circle.radius,
            circle.center.y - circle.radius,
            circle.radius * 2.0,
            circle.radius * 2.0,
        )
        drawn = False
        if isinstance(circle.fill, SolidPaint):
            paint = self._paint_from_solid(circle.fill)
            if paint:
                canvas.drawOval(rect, paint)
                drawn = True
        if circle.stroke and isinstance(circle.stroke.paint, SolidPaint):
            paint = self._paint_from_stroke(circle.stroke)
            if paint:
                canvas.drawOval(rect, paint)
                drawn = True
        return drawn

    def _draw_ellipse(self, canvas: "skia.Canvas", ellipse: Ellipse) -> bool:
        rect = skia.Rect.MakeXYWH(
            ellipse.center.x - ellipse.radius_x,
            ellipse.center.y - ellipse.radius_y,
            ellipse.radius_x * 2.0,
            ellipse.radius_y * 2.0,
        )
        drawn = False
        if isinstance(ellipse.fill, SolidPaint):
            paint = self._paint_from_solid(ellipse.fill)
            if paint:
                canvas.drawOval(rect, paint)
                drawn = True
        if ellipse.stroke and isinstance(ellipse.stroke.paint, SolidPaint):
            paint = self._paint_from_stroke(ellipse.stroke)
            if paint:
                canvas.drawOval(rect, paint)
                drawn = True
        return drawn

    def _draw_path(self, canvas: "skia.Canvas", path: IRPath) -> bool:
        if not path.segments:
            return False
        sk_path = self._build_skia_path(path.segments, path.is_closed)
        drawn = False
        if isinstance(path.fill, SolidPaint):
            paint = self._paint_from_solid(path.fill)
            if paint:
                canvas.drawPath(sk_path, paint)
                drawn = True
        if path.stroke and isinstance(path.stroke.paint, SolidPaint):
            paint = self._paint_from_stroke(path.stroke)
            if paint:
                canvas.drawPath(sk_path, paint)
                drawn = True
        return drawn

    def _paint_from_solid(self, paint: SolidPaint) -> "skia.Paint | None":
        color = self._color_from_hex(paint.rgb, paint.opacity)
        if color is None:
            return None
        sk_paint = skia.Paint(AntiAlias=True)
        sk_paint.setStyle(skia.Paint.kFill_Style)
        sk_paint.setColor4f(color)
        return sk_paint

    def _paint_from_stroke(self, stroke: Stroke) -> "skia.Paint | None":
        if not isinstance(stroke.paint, SolidPaint):
            return None
        color = self._color_from_hex(stroke.paint.rgb, stroke.opacity)
        if color is None:
            return None
        sk_paint = skia.Paint(AntiAlias=True)
        sk_paint.setStyle(skia.Paint.kStroke_Style)
        sk_paint.setColor4f(color)
        sk_paint.setStrokeWidth(max(stroke.width, 0.1))
        cap_map = {
            StrokeCap.BUTT: skia.Paint.Cap.kButt_Cap,
            StrokeCap.ROUND: skia.Paint.Cap.kRound_Cap,
            StrokeCap.SQUARE: skia.Paint.Cap.kSquare_Cap,
        }
        sk_paint.setStrokeCap(cap_map.get(stroke.cap, skia.Paint.Cap.kButt_Cap))
        join_map = {
            StrokeJoin.MITER: skia.Paint.Join.kMiter_Join,
            StrokeJoin.ROUND: skia.Paint.Join.kRound_Join,
            StrokeJoin.BEVEL: skia.Paint.Join.kBevel_Join,
        }
        sk_paint.setStrokeJoin(join_map.get(stroke.join, skia.Paint.Join.kMiter_Join))
        if stroke.dash_array:
            intervals = [max(0.1, float(value)) for value in stroke.dash_array if value > 0]
            if intervals:
                effect = skia.DashPathEffect.Make(intervals, stroke.dash_offset or 0.0)
                if effect:
                    sk_paint.setPathEffect(effect)
        return sk_paint

    def _build_skia_path(self, segments: Iterable[SegmentType], closed: bool) -> "skia.Path":
        segment_list = list(segments)
        path = skia.Path()
        if not segment_list:
            return path
        first_segment = segment_list[0]
        path.moveTo(first_segment.start.x, first_segment.start.y)
        for segment in segment_list:
            if isinstance(segment, LineSegment):
                path.lineTo(segment.end.x, segment.end.y)
            elif isinstance(segment, BezierSegment):
                path.cubicTo(
                    segment.control1.x,
                    segment.control1.y,
                    segment.control2.x,
                    segment.control2.y,
                    segment.end.x,
                    segment.end.y,
                )
        if closed:
            path.close()
        return path

    # ------------------------------------------------------------------ #
    # Utility helpers
    # ------------------------------------------------------------------ #

    def _expanded_bounds(self, element) -> Rect:
        bounds = self._element_bounds(element)
        pad = 0.5
        stroke = getattr(element, "stroke", None)
        if isinstance(stroke, Stroke) and stroke.paint is not None:
            pad = max(pad, stroke.width / 2.0)
        return Rect(bounds.x - pad, bounds.y - pad, bounds.width + pad * 2.0, bounds.height + pad * 2.0)

    def _element_bounds(self, element) -> Rect:
        if isinstance(element, Rectangle):
            return element.bounds
        if isinstance(element, Circle):
            return element.bbox
        if isinstance(element, Ellipse):
            return element.bbox
        if isinstance(element, IRPath):
            return compute_path_bounds(element.segments or [])
        raise TypeError(f"Unsupported element type for rasterization: {type(element).__name__}")

    @staticmethod
    def _color_from_hex(value: str, opacity: float) -> "skia.Color4f | None":
        value = value.strip().lstrip("#")
        if len(value) != 6:
            return None
        try:
            r = int(value[0:2], 16) / 255.0
            g = int(value[2:4], 16) / 255.0
            b = int(value[4:6], 16) / 255.0
        except ValueError:
            return None
        a = max(0.0, min(1.0, opacity))
        return skia.Color4f(r, g, b, a)


__all__ = ["Rasterizer", "RasterResult", "SKIA_AVAILABLE"]
