"""Shape drawing helpers for DrawingML rasterization."""

from __future__ import annotations

from svg2ooxml.drawingml.rasterizer_backend import skia
from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.scene import Group
from svg2ooxml.ir.scene import Path as IRPath
from svg2ooxml.ir.shapes import Circle, Ellipse, Rectangle


class RasterizerShapeMixin:
    def _draw_element(self, canvas, element) -> bool:
        """Draw a single IR element onto a canvas. Returns True on success."""
        try:
            geometry_bounds = self._element_bounds(element)
        except TypeError:
            return False
        if isinstance(element, Rectangle):
            return self._draw_rectangle(canvas, element, geometry_bounds)
        if isinstance(element, Circle):
            return self._draw_circle(canvas, element, geometry_bounds)
        if isinstance(element, Ellipse):
            return self._draw_ellipse(canvas, element, geometry_bounds)
        if isinstance(element, IRPath):
            return self._draw_path(canvas, element, geometry_bounds)
        if isinstance(element, Group):
            drawn_any = False
            if element.opacity < 1.0:
                canvas.saveLayerAlpha(None, int(round(element.opacity * 255)))
            else:
                canvas.save()
            try:
                for child in element.children:
                    if self._draw_element(canvas, child):
                        drawn_any = True
            finally:
                canvas.restore()
            return drawn_any
        return False

    def _draw_rectangle(self, canvas: skia.Canvas, rect: Rectangle, bounds: Rect) -> bool:
        sk_rect = skia.Rect.MakeXYWH(
            rect.bounds.x,
            rect.bounds.y,
            rect.bounds.width,
            rect.bounds.height,
        )
        drawn = False
        if rect.fill is not None:
            paint = self._paint_from_fill(rect.fill, bounds, opacity=rect.opacity)
            if paint:
                canvas.drawRect(sk_rect, paint)
                drawn = True
        if rect.stroke and rect.stroke.paint is not None:
            paint = self._paint_from_stroke(rect.stroke, bounds, opacity=rect.opacity)
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
            paint = self._paint_from_fill(circle.fill, bounds, opacity=circle.opacity)
            if paint:
                canvas.drawOval(rect, paint)
                drawn = True
        if circle.stroke and circle.stroke.paint is not None:
            paint = self._paint_from_stroke(circle.stroke, bounds, opacity=circle.opacity)
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
            paint = self._paint_from_fill(ellipse.fill, bounds, opacity=ellipse.opacity)
            if paint:
                canvas.drawOval(rect, paint)
                drawn = True
        if ellipse.stroke and ellipse.stroke.paint is not None:
            paint = self._paint_from_stroke(ellipse.stroke, bounds, opacity=ellipse.opacity)
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
            paint = self._paint_from_fill(path.fill, bounds, opacity=path.opacity)
            if paint:
                canvas.drawPath(sk_path, paint)
                drawn = True
        if path.stroke and path.stroke.paint is not None:
            paint = self._paint_from_stroke(path.stroke, bounds, opacity=path.opacity)
            if paint:
                canvas.drawPath(sk_path, paint)
                drawn = True
        return drawn


__all__ = ["RasterizerShapeMixin"]
