"""Tessellation scaffolding for fill and stroke paths."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .path_normalizer import NormalizedPath
from .primitives import ClosePath, LineTo, MoveTo

Point = tuple[float, float]


def _polygon_area(points: list[Point]) -> float:
    area = 0.0
    if len(points) < 3:
        return 0.0
    for idx in range(len(points) - 1):
        x1, y1 = points[idx]
        x2, y2 = points[idx + 1]
        area += (x1 * y2) - (x2 * y1)
    return area * 0.5


@dataclass(slots=True)
class TessellationResult:
    contours: list[list[Point]]
    stroke_width: float | None
    winding_rule: str
    areas: list[float]
    stroke_outline: list[list[Point]] | None = None


class Tessellator:
    """Converts normalized paths into contour lists for raster backends."""

    def tessellate_fill(
        self,
        path: NormalizedPath,
        tolerance: float = 0.25,
        winding_rule: str = "nonzero",
    ) -> TessellationResult:
        contours: list[list[Point]] = []
        current: list[Point] = []
        start: Point | None = None

        for prim in path.to_primitives(tolerance=tolerance):
            if isinstance(prim, MoveTo):
                if current:
                    if start and current[-1] != start:
                        current.append(start)
                    contours.append(current)
                    current = []
                point = (prim.x, prim.y)
                current.append(point)
                start = point
            elif isinstance(prim, LineTo):
                current.append((prim.x, prim.y))
            elif isinstance(prim, ClosePath):
                if current:
                    if start and current[-1] != start:
                        current.append(start)
                    contours.append(current)
                    current = []
                    start = None
            else:
                continue

        if current:
            if start and current[-1] != start:
                current.append(start)
            contours.append(current)

        areas = [_polygon_area(points) for points in contours]
        return TessellationResult(
            contours=contours,
            stroke_width=path.stroke_width,
            winding_rule=winding_rule,
            areas=areas,
        )

    def tessellate_stroke(
        self,
        path: NormalizedPath,
        tolerance: float = 0.25,
    ) -> TessellationResult:
        fill_result = self.tessellate_fill(path, tolerance)
        stroke_width = path.stroke_width or 0.0
        if stroke_width > 0 and fill_result.contours:
            offset = stroke_width / 2.0
            outlines: list[list[Point]] = []
            for contour in fill_result.contours:
                if len(contour) < 2:
                    continue
                outline: list[Point] = []
                for idx, point in enumerate(contour):
                    prev = contour[idx - 1] if idx > 0 else contour[idx]
                    nxt = contour[idx + 1] if idx + 1 < len(contour) else contour[idx]
                    vx = nxt[0] - prev[0]
                    vy = nxt[1] - prev[1]
                    length = math.hypot(vx, vy)
                    if length == 0:
                        outline.append(point)
                        continue
                    nx = -vy / length
                    ny = vx / length
                    outline.append((point[0] + nx * offset, point[1] + ny * offset))
                outlines.append(outline)
            fill_result.stroke_outline = outlines
        else:
            fill_result.stroke_outline = None
        return fill_result
