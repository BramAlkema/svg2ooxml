"""Tessellation rasterisation helpers."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from svg2ooxml.common.units import UnitConverter
from svg2ooxml.common.units.lengths import resolve_length_px
from svg2ooxml.core.resvg.geometry.tessellation import TessellationResult
from svg2ooxml.core.resvg.usvg_tree import Tree

PixelPoint = tuple[float, float]


@dataclass(frozen=True)
class Viewport:
    """Mapping between SVG user space and raster pixels."""

    width: int
    height: int
    min_x: float
    min_y: float
    scale_x: float
    scale_y: float

    @classmethod
    def from_tree(cls, tree: Tree, default_size: float = 256.0) -> Viewport:
        root = tree.root
        view_box = root.view_box
        converter = UnitConverter()
        default_context = converter.create_context(
            width=default_size,
            height=default_size,
            parent_width=default_size,
            parent_height=default_size,
            viewport_width=default_size,
            viewport_height=default_size,
        )

        def _parse_dimension(value: str | None, *, axis: str) -> float | None:
            if value is None:
                return None
            token = value.strip()
            if not token:
                return None
            resolved = resolve_length_px(
                token,
                default_context,
                axis=axis,
                default=math.nan,
                unit_converter=converter,
            )
            if math.isnan(resolved):
                return None
            return resolved

        width_attr = _parse_dimension(root.attributes.get("width"), axis="x")
        height_attr = _parse_dimension(root.attributes.get("height"), axis="y")

        if view_box:
            min_x, min_y, vb_width, vb_height = view_box
            user_width = vb_width if vb_width > 0 else default_size
            user_height = vb_height if vb_height > 0 else default_size
        else:
            min_x = 0.0
            min_y = 0.0
            user_width = width_attr if width_attr and width_attr > 0 else default_size
            user_height = height_attr if height_attr and height_attr > 0 else default_size

        pixel_width = width_attr if width_attr and width_attr > 0 else user_width
        pixel_height = height_attr if height_attr and height_attr > 0 else user_height

        width_px = max(1, int(math.ceil(pixel_width)))
        height_px = max(1, int(math.ceil(pixel_height)))

        scale_x = width_px / user_width if user_width else 1.0
        scale_y = height_px / user_height if user_height else 1.0

        return cls(
            width=width_px,
            height=height_px,
            min_x=min_x,
            min_y=min_y,
            scale_x=scale_x,
            scale_y=scale_y,
        )

    def to_pixel(self, x: float, y: float) -> PixelPoint:
        px = (x - self.min_x) * self.scale_x
        py = (y - self.min_y) * self.scale_y
        return px, py

    def to_user(self, px: np.ndarray | float, py: np.ndarray | float) -> tuple[np.ndarray, np.ndarray]:
        x = (np.asarray(px, dtype=np.float32) / self.scale_x) + self.min_x
        y = (np.asarray(py, dtype=np.float32) / self.scale_y) + self.min_y
        return x, y


class Rasterizer:
    """Convert tessellated contours into alpha masks."""

    def rasterize_fill(self, tessellation: TessellationResult, viewport: Viewport) -> np.ndarray:
        if not tessellation.contours:
            return np.zeros((viewport.height, viewport.width), dtype=bool)

        pixel_contours = [_to_pixel_contour(contour, viewport) for contour in tessellation.contours]
        return _scanline_fill(pixel_contours, viewport, tessellation.winding_rule)


def _to_pixel_contour(contour: Sequence[tuple[float, float]], viewport: Viewport) -> np.ndarray:
    if not contour:
        return np.empty((0, 2), dtype=np.float32)
    points = [viewport.to_pixel(x, y) for x, y in contour]
    if points[0] != points[-1]:
        points.append(points[0])
    return np.asarray(points, dtype=np.float32)


def _scanline_fill(contours: Iterable[np.ndarray], viewport: Viewport, winding_rule: str) -> np.ndarray:
    mask = np.zeros((viewport.height, viewport.width), dtype=bool)
    bounds = _collect_bounds(contours)
    if bounds is None:
        return mask

    min_x, min_y, max_x, max_y, prepared = bounds
    x_start = max(0, int(math.floor(min_x)))
    x_end = min(viewport.width, int(math.floor(max_x)) + 1)
    y_start = max(0, int(math.floor(min_y)))
    y_end = min(viewport.height, int(math.floor(max_y)) + 1)

    if x_start >= x_end or y_start >= y_end:
        return mask

    for y_idx in range(y_start, y_end):
        y = y_idx + 0.5
        for x_idx in range(x_start, x_end):
            x = x_idx + 0.5
            winding = 0
            for contour in prepared:
                winding += _winding_for_contour(contour, x, y)
            if winding_rule == "nonzero":
                inside = winding != 0
            else:
                inside = winding % 2 != 0
            if inside:
                mask[y_idx, x_idx] = True
    return mask


def _collect_bounds(contours: Iterable[np.ndarray]) -> tuple[float, float, float, float, list[np.ndarray]] | None:
    prepared: list[np.ndarray] = []
    min_x = math.inf
    min_y = math.inf
    max_x = -math.inf
    max_y = -math.inf
    for contour in contours:
        if contour.size == 0:
            continue
        prepared.append(contour)
        xs = contour[:, 0]
        ys = contour[:, 1]
        min_x = min(min_x, float(xs.min()))
        min_y = min(min_y, float(ys.min()))
        max_x = max(max_x, float(xs.max()))
        max_y = max(max_y, float(ys.max()))
    if not prepared:
        return None
    return min_x, min_y, max_x, max_y, prepared


def _winding_for_contour(contour: np.ndarray, x: float, y: float) -> int:
    winding = 0
    if contour.shape[0] < 2:
        return 0
    for idx in range(contour.shape[0] - 1):
        x0 = float(contour[idx, 0])
        y0 = float(contour[idx, 1])
        x1 = float(contour[idx + 1, 0])
        y1 = float(contour[idx + 1, 1])
        if y0 <= y:
            if y1 > y and _is_left(x0, y0, x1, y1, x, y) > 0:
                winding += 1
        else:
            if y1 <= y and _is_left(x0, y0, x1, y1, x, y) < 0:
                winding -= 1
    return winding


def _is_left(x0: float, y0: float, x1: float, y1: float, x2: float, y2: float) -> float:
    return (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)


__all__ = ["Viewport", "Rasterizer"]
