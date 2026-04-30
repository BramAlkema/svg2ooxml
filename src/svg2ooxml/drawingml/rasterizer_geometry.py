"""Geometry helpers for DrawingML rasterization."""

from __future__ import annotations

from collections.abc import Iterable

from svg2ooxml.common.geometry.paths.drawingml import compute_path_bounds
from svg2ooxml.drawingml.rasterizer_backend import skia
from svg2ooxml.drawingml.skia_path import skia_path_from_segments
from svg2ooxml.ir.geometry import Rect, SegmentType
from svg2ooxml.ir.paint import Stroke
from svg2ooxml.ir.scene import Group, Image
from svg2ooxml.ir.scene import Path as IRPath
from svg2ooxml.ir.shapes import Circle, Ellipse, Rectangle


class RasterizerGeometryMixin:
    def _build_skia_path(
        self,
        segments: Iterable[SegmentType],
        closed: bool,
        fill_rule: str | None = None,
    ) -> skia.Path:
        path = skia_path_from_segments(
            list(segments),
            closed=closed,
            fill_rule=fill_rule,
        )
        return path if path is not None else skia.Path()

    def _clip_path(self, element) -> skia.Path | None:
        clip = getattr(element, "clip", None)
        if clip is None:
            return None
        if getattr(clip, "is_empty", False):
            return skia.Path()
        skia_clip = getattr(clip, "skia_path", None)
        if skia_clip is not None:
            try:
                return skia.Path(skia_clip)
            except Exception:
                return skia_clip
        segments = getattr(clip, "path_segments", None)
        if segments:
            return self._build_skia_path(segments, True)
        return None

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
