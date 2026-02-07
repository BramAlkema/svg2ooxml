"""Rasterizer that renders IR elements to PNG using skia-python."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Rect, SegmentType
from svg2ooxml.ir.paint import (
    GradientStop,
    LinearGradientPaint,
    RadialGradientPaint,
    SolidPaint,
    Stroke,
    StrokeCap,
    StrokeJoin,
)
from svg2ooxml.ir.scene import Group, Image
from svg2ooxml.ir.scene import Path as IRPath
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

        geometry_bounds = self._element_bounds(element)
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
            drawn = self._draw_rectangle(canvas, element, geometry_bounds)
        elif isinstance(element, Circle):
            drawn = self._draw_circle(canvas, element, geometry_bounds)
        elif isinstance(element, Ellipse):
            drawn = self._draw_ellipse(canvas, element, geometry_bounds)
        elif isinstance(element, IRPath):
            drawn = self._draw_path(canvas, element, geometry_bounds)
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

    def _draw_rectangle(self, canvas: skia.Canvas, rect: Rectangle, bounds: Rect) -> bool:
        sk_rect = skia.Rect.MakeXYWH(rect.bounds.x, rect.bounds.y, rect.bounds.width, rect.bounds.height)
        drawn = False
        if rect.fill is not None:
            paint = self._paint_from_fill(rect.fill, bounds)
            if paint:
                canvas.drawRect(sk_rect, paint)
                drawn = True
        if rect.stroke and rect.stroke.paint is not None:
            paint = self._paint_from_stroke(rect.stroke, bounds)
            if paint:
                canvas.drawRect(sk_rect, paint)
                drawn = True
        return drawn

    def _draw_circle(self, canvas: skia.Canvas, circle: Circle, bounds: Rect) -> bool:
        rect = skia.Rect.MakeXYWH(
            circle.center.x - circle.radius,
            circle.center.y - circle.radius,
            circle.radius * 2.0,
            circle.radius * 2.0,
        )
        drawn = False
        if circle.fill is not None:
            paint = self._paint_from_fill(circle.fill, bounds)
            if paint:
                canvas.drawOval(rect, paint)
                drawn = True
        if circle.stroke and circle.stroke.paint is not None:
            paint = self._paint_from_stroke(circle.stroke, bounds)
            if paint:
                canvas.drawOval(rect, paint)
                drawn = True
        return drawn

    def _draw_ellipse(self, canvas: skia.Canvas, ellipse: Ellipse, bounds: Rect) -> bool:
        rect = skia.Rect.MakeXYWH(
            ellipse.center.x - ellipse.radius_x,
            ellipse.center.y - ellipse.radius_y,
            ellipse.radius_x * 2.0,
            ellipse.radius_y * 2.0,
        )
        drawn = False
        if ellipse.fill is not None:
            paint = self._paint_from_fill(ellipse.fill, bounds)
            if paint:
                canvas.drawOval(rect, paint)
                drawn = True
        if ellipse.stroke and ellipse.stroke.paint is not None:
            paint = self._paint_from_stroke(ellipse.stroke, bounds)
            if paint:
                canvas.drawOval(rect, paint)
                drawn = True
        return drawn

    def _draw_path(self, canvas: skia.Canvas, path: IRPath, bounds: Rect) -> bool:
        if not path.segments:
            return False
        sk_path = self._build_skia_path(path.segments, path.is_closed)
        drawn = False
        if path.fill is not None:
            paint = self._paint_from_fill(path.fill, bounds)
            if paint:
                canvas.drawPath(sk_path, paint)
                drawn = True
        if path.stroke and path.stroke.paint is not None:
            paint = self._paint_from_stroke(path.stroke, bounds)
            if paint:
                canvas.drawPath(sk_path, paint)
                drawn = True
        return drawn

    def _paint_from_fill(self, paint, bounds: Rect) -> skia.Paint | None:
        sk_paint = skia.Paint(AntiAlias=True)
        sk_paint.setStyle(skia.Paint.kFill_Style)
        if self._apply_paint(sk_paint, paint, bounds, opacity=1.0):
            return sk_paint
        return None

    def _paint_from_stroke(self, stroke: Stroke, bounds: Rect) -> skia.Paint | None:
        sk_paint = skia.Paint(AntiAlias=True)
        sk_paint.setStyle(skia.Paint.kStroke_Style)
        if not self._apply_paint(sk_paint, stroke.paint, bounds, opacity=stroke.opacity):
            return None
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

    def _apply_paint(self, sk_paint: skia.Paint, paint, bounds: Rect, *, opacity: float) -> bool:
        if isinstance(paint, SolidPaint):
            color = self._color_from_hex(paint.rgb, paint.opacity * opacity)
            if color is None:
                return False
            sk_paint.setColor4f(color)
            return True
        if isinstance(paint, LinearGradientPaint):
            shader = self._linear_gradient_shader(paint, bounds, opacity)
            if shader is None:
                return False
            sk_paint.setShader(shader)
            return True
        if isinstance(paint, RadialGradientPaint):
            shader = self._radial_gradient_shader(paint, bounds, opacity)
            if shader is None:
                return False
            sk_paint.setShader(shader)
            return True
        return False

    def _linear_gradient_shader(
        self,
        paint: LinearGradientPaint,
        bounds: Rect,
        opacity: float,
    ) -> skia.Shader | None:
        prepared = self._prepare_gradient_stops(paint.stops, opacity)
        if prepared is None:
            return None
        positions, colors = prepared
        x1, y1, x2, y2 = self._linear_gradient_points(paint, bounds)
        if x1 == x2 and y1 == y2:
            return None
        tile_mode = self._resolve_tile_mode(paint.spread_method)
        matrix = self._to_skia_matrix(paint.transform)
        try:
            return skia.GradientShader.MakeLinear(
                [skia.Point(x1, y1), skia.Point(x2, y2)],
                colors,
                positions,
                tile_mode,
                0,
                matrix,
            )
        except TypeError:  # pragma: no cover - older skia signature
            return skia.GradientShader.MakeLinear(
                [skia.Point(x1, y1), skia.Point(x2, y2)],
                colors,
                positions,
                tile_mode,
            )

    def _radial_gradient_shader(
        self,
        paint: RadialGradientPaint,
        bounds: Rect,
        opacity: float,
    ) -> skia.Shader | None:
        prepared = self._prepare_gradient_stops(paint.stops, opacity)
        if prepared is None:
            return None
        positions, colors = prepared
        cx, cy, radius = self._radial_gradient_params(paint, bounds)
        if radius <= 0:
            return None
        fx, fy = self._radial_gradient_focus(paint, bounds, (cx, cy))
        tile_mode = self._resolve_tile_mode(paint.spread_method)
        matrix = self._to_skia_matrix(paint.transform)
        if fx != cx or fy != cy:
            try:
                return skia.GradientShader.MakeTwoPointConical(
                    skia.Point(fx, fy),
                    0.0,
                    skia.Point(cx, cy),
                    radius,
                    colors,
                    positions,
                    tile_mode,
                    0,
                    matrix,
                )
            except TypeError:  # pragma: no cover - older skia signature
                return skia.GradientShader.MakeTwoPointConical(
                    skia.Point(fx, fy),
                    0.0,
                    skia.Point(cx, cy),
                    radius,
                    colors,
                    positions,
                    tile_mode,
                )
        try:
            return skia.GradientShader.MakeRadial(
                skia.Point(cx, cy),
                radius,
                colors,
                positions,
                tile_mode,
                0,
                matrix,
            )
        except TypeError:  # pragma: no cover - older skia signature
            return skia.GradientShader.MakeRadial(
                skia.Point(cx, cy),
                radius,
                colors,
                positions,
                tile_mode,
            )

    def _build_skia_path(self, segments: Iterable[SegmentType], closed: bool) -> skia.Path:
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

    def _prepare_gradient_stops(
        self,
        stops: Iterable[GradientStop],
        opacity: float,
    ) -> tuple[list[float], list[skia.Color4f]] | None:
        positions: list[float] = []
        colors: list[skia.Color4f] = []
        for stop in stops:
            offset = max(0.0, min(1.0, float(stop.offset)))
            color = self._color_from_hex(stop.rgb, float(stop.opacity) * opacity)
            if color is None:
                continue
            positions.append(offset)
            colors.append(color)
        if len(colors) < 2:
            return None
        return positions, colors

    def _linear_gradient_points(
        self,
        paint: LinearGradientPaint,
        bounds: Rect,
    ) -> tuple[float, float, float, float]:
        x1, y1 = paint.start
        x2, y2 = paint.end
        if paint.gradient_units == "objectBoundingBox":
            x1 = bounds.x + x1 * bounds.width
            y1 = bounds.y + y1 * bounds.height
            x2 = bounds.x + x2 * bounds.width
            y2 = bounds.y + y2 * bounds.height
        return x1, y1, x2, y2

    def _radial_gradient_params(
        self,
        paint: RadialGradientPaint,
        bounds: Rect,
    ) -> tuple[float, float, float]:
        cx, cy = paint.center
        radius = paint.radius
        if paint.gradient_units == "objectBoundingBox":
            cx = bounds.x + cx * bounds.width
            cy = bounds.y + cy * bounds.height
            radius = radius * (bounds.width + bounds.height) * 0.5
        return cx, cy, radius

    def _radial_gradient_focus(
        self,
        paint: RadialGradientPaint,
        bounds: Rect,
        center: tuple[float, float],
    ) -> tuple[float, float]:
        if paint.focal_point is None:
            return center
        fx, fy = paint.focal_point
        if paint.gradient_units == "objectBoundingBox":
            fx = bounds.x + fx * bounds.width
            fy = bounds.y + fy * bounds.height
        return fx, fy

    @staticmethod
    def _resolve_tile_mode(spread_method: str | None):
        if spread_method == "repeat":
            return skia.TileMode.kRepeat
        if spread_method == "reflect":
            return skia.TileMode.kMirror
        return skia.TileMode.kClamp

    @staticmethod
    def _to_skia_matrix(matrix) -> skia.Matrix | None:
        if matrix is None:
            return None
        try:
            return skia.Matrix.MakeAll(
                float(matrix[0][0]),
                float(matrix[0][1]),
                float(matrix[0][2]),
                float(matrix[1][0]),
                float(matrix[1][1]),
                float(matrix[1][2]),
                float(matrix[2][0]),
                float(matrix[2][1]),
                float(matrix[2][2]),
            )
        except Exception:  # pragma: no cover - defensive for unexpected matrix shapes
            return None

    @staticmethod
    def _color_from_hex(value: str, opacity: float) -> skia.Color4f | None:
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
