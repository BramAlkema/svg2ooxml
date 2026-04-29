"""Paint and shader helpers for DrawingML rasterization."""

from __future__ import annotations

from collections.abc import Iterable

from svg2ooxml.common.dash_patterns import normalize_dash_array
from svg2ooxml.common.gradient_units import normalize_gradient_units
from svg2ooxml.common.skia_helpers import tile_mode as _skia_tile_mode
from svg2ooxml.core.resvg.geometry.matrix_bridge import matrix_to_tuple
from svg2ooxml.drawingml.rasterizer_backend import skia
from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.paint import (
    GradientStop,
    LinearGradientPaint,
    RadialGradientPaint,
    SolidPaint,
    Stroke,
    StrokeCap,
    StrokeJoin,
)


class RasterizerPaintMixin:
    def _paint_from_fill(
        self,
        paint,
        bounds: Rect,
        *,
        opacity: float = 1.0,
    ) -> skia.Paint | None:
        sk_paint = skia.Paint(AntiAlias=True)
        sk_paint.setStyle(skia.Paint.kFill_Style)
        if self._apply_paint(sk_paint, paint, bounds, opacity=opacity):
            return sk_paint
        return None

    def _paint_from_stroke(
        self,
        stroke: Stroke,
        bounds: Rect,
        *,
        opacity: float = 1.0,
    ) -> skia.Paint | None:
        sk_paint = skia.Paint(AntiAlias=True)
        sk_paint.setStyle(skia.Paint.kStroke_Style)
        if not self._apply_paint(
            sk_paint,
            stroke.paint,
            bounds,
            opacity=stroke.opacity * opacity,
        ):
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
            intervals = [
                max(0.1, value) for value in normalize_dash_array(stroke.dash_array)
            ]
            if intervals:
                effect = skia.DashPathEffect.Make(intervals, stroke.dash_offset or 0.0)
                if effect:
                    sk_paint.setPathEffect(effect)
        return sk_paint

    def _apply_paint(
        self,
        sk_paint: skia.Paint,
        paint,
        bounds: Rect,
        *,
        opacity: float,
    ) -> bool:
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

    def _prepare_gradient_stops(
        self,
        stops: Iterable[GradientStop],
        opacity: float,
    ) -> tuple[list[float], list[skia.Color4f]] | None:
        positions: list[float] = []
        colors: list[skia.Color4f] = []
        last_offset = 0.0
        for stop in stops:
            offset = max(0.0, min(1.0, float(stop.offset)))
            offset = max(offset, last_offset)
            last_offset = offset
            color = self._color_from_hex(stop.rgb, float(stop.opacity) * opacity)
            if color is None:
                continue
            positions.append(offset)
            colors.append(color)
        if len(colors) < 2:
            return None
        return positions, colors

    @staticmethod
    def _linear_gradient_points(
        paint: LinearGradientPaint,
        bounds: Rect,
    ) -> tuple[float, float, float, float]:
        x1, y1 = paint.start
        x2, y2 = paint.end
        if normalize_gradient_units(paint.gradient_units) == "objectBoundingBox":
            x1 = bounds.x + x1 * bounds.width
            y1 = bounds.y + y1 * bounds.height
            x2 = bounds.x + x2 * bounds.width
            y2 = bounds.y + y2 * bounds.height
        return x1, y1, x2, y2

    @staticmethod
    def _radial_gradient_params(
        paint: RadialGradientPaint,
        bounds: Rect,
    ) -> tuple[float, float, float]:
        cx, cy = paint.center
        radius = paint.radius
        if normalize_gradient_units(paint.gradient_units) == "objectBoundingBox":
            cx = bounds.x + cx * bounds.width
            cy = bounds.y + cy * bounds.height
            radius = radius * (bounds.width + bounds.height) * 0.5
        return cx, cy, radius

    @staticmethod
    def _radial_gradient_focus(
        paint: RadialGradientPaint,
        bounds: Rect,
        center: tuple[float, float],
    ) -> tuple[float, float]:
        if paint.focal_point is None:
            return center
        fx, fy = paint.focal_point
        if normalize_gradient_units(paint.gradient_units) == "objectBoundingBox":
            fx = bounds.x + fx * bounds.width
            fy = bounds.y + fy * bounds.height
        return fx, fy

    _resolve_tile_mode = staticmethod(
        lambda spread_method: _skia_tile_mode(skia, spread_method)
    )

    @staticmethod
    def _to_skia_matrix(matrix) -> skia.Matrix | None:
        if matrix is None:
            return None
        try:
            a, b, c, d, e, f = matrix_to_tuple(matrix)
            return skia.Matrix.MakeAll(
                a,
                c,
                e,
                b,
                d,
                f,
                0.0,
                0.0,
                1.0,
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


__all__ = ["RasterizerPaintMixin"]
