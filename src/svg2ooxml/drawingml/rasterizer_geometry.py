"""Geometry helpers for DrawingML rasterization."""

from __future__ import annotations

from collections.abc import Iterable

from svg2ooxml.common.geometry.paths.drawingml import compute_path_bounds
from svg2ooxml.drawingml.rasterizer_backend import skia
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Rect, SegmentType
from svg2ooxml.ir.paint import Stroke
from svg2ooxml.ir.scene import Group, Image
from svg2ooxml.ir.scene import Path as IRPath
from svg2ooxml.ir.shapes import Circle, Ellipse, Rectangle


class RasterizerGeometryMixin:
    def _build_skia_path(
        self,
        segments: Iterable[SegmentType],
        closed: bool,
    ) -> skia.Path:
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

    def _expanded_bounds(self, element) -> Rect:
        bounds = self._element_bounds(element)
        pad = 0.5
        stroke = getattr(element, "stroke", None)
        if isinstance(stroke, Stroke) and stroke.paint is not None:
            pad = max(pad, stroke.width / 2.0)
        return Rect(
            bounds.x - pad,
            bounds.y - pad,
            bounds.width + pad * 2.0,
            bounds.height + pad * 2.0,
        )

    def _group_bounds(self, group: Group) -> Rect:
        boxes: list[Rect] = []
        for child in group.children:
            if isinstance(child, Group):
                child_bounds = self._group_bounds(child)
                if child_bounds.width > 0 and child_bounds.height > 0:
                    boxes.append(child_bounds)
                continue
            if isinstance(child, Image):
                continue
            try:
                boxes.append(self._expanded_bounds(child))
            except TypeError:
                continue
        if not boxes:
            return Rect(0.0, 0.0, 0.0, 0.0)
        min_x = min(box.x for box in boxes)
        min_y = min(box.y for box in boxes)
        max_x = max(box.x + box.width for box in boxes)
        max_y = max(box.y + box.height for box in boxes)
        return Rect(min_x, min_y, max_x - min_x, max_y - min_y)

    @staticmethod
    def _element_bounds(element) -> Rect:
        if isinstance(element, Rectangle):
            return element.bounds
        if isinstance(element, Circle):
            return element.bbox
        if isinstance(element, Ellipse):
            return element.bbox
        if isinstance(element, IRPath):
            return compute_path_bounds(element.segments or [])
        raise TypeError(
            f"Unsupported element type for rasterization: {type(element).__name__}"
        )


__all__ = ["RasterizerGeometryMixin"]
