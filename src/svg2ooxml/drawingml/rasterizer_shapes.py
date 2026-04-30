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
        if isinstance(element, Group):
            return self._draw_group(canvas, element)
        try:
            geometry_bounds = self._element_bounds(element)
        except TypeError:
            return False
        clip_path = self._clip_path(element)
        if clip_path is not None:
            if clip_path.isEmpty():
                return False
            canvas.save()
            canvas.clipPath(clip_path, skia.ClipOp.kIntersect, True)
            try:
                return self._draw_unclipped_element(canvas, element, geometry_bounds)
            finally:
                canvas.restore()
        return self._draw_unclipped_element(canvas, element, geometry_bounds)

    def _draw_unclipped_element(self, canvas, element, geometry_bounds: Rect) -> bool:
        if isinstance(element, Rectangle):
            return self._draw_rectangle(canvas, element, geometry_bounds)
        if isinstance(element, Circle):
            return self._draw_circle(canvas, element, geometry_bounds)
        if isinstance(element, Ellipse):
            return self._draw_ellipse(canvas, element, geometry_bounds)
        if isinstance(element, IRPath):
            return self._draw_path(canvas, element, geometry_bounds)
        return False

    def _draw_group(self, canvas, element: Group) -> bool:
        drawn_any = False
        clip_path = self._clip_path(element)
        if clip_path is not None and clip_path.isEmpty():
            return False
        if element.opacity < 1.0:
            canvas.saveLayerAlpha(None, int(round(element.opacity * 255)))
        else:
            canvas.save()
        try:
            if clip_path is not None:
                canvas.clipPath(clip_path, skia.ClipOp.kIntersect, True)
            for child in element.children:
                if self._draw_element(canvas, child):
                    drawn_any = True
        finally:
            canvas.restore()
        return drawn_any

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
        fill_rule = None
        if isinstance(path.metadata, dict):
            fill_rule = path.metadata.get("fill_rule")
        sk_path = self._build_skia_path(
            path.segments,
            path.is_closed,
            fill_rule=fill_rule if isinstance(fill_rule, str) else None,
        )
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
