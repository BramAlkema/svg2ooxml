"""Geometry and tessellation scaffolding."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point
from svg2ooxml.ir.scene import Path as IRPath
from svg2ooxml.ir.shapes import Circle, Ellipse, Rectangle


@dataclass(slots=True)
class TessellationResult:
    contours: Sequence[np.ndarray]
    winding_rule: str
    areas: Sequence[float]
    stroke_width: float | None = None
    stroke_outline: Sequence[np.ndarray] | None = None


class Tessellator:
    """Simplified tessellator for primitive shapes and paths."""

    def tessellate_geometry(self, geometry) -> TessellationResult:
        if geometry is None:
            return TessellationResult(contours=[], winding_rule="nonzero", areas=[], stroke_width=None)
        if isinstance(geometry, Rectangle):
            return self._tessellate_rectangle(geometry)
        if isinstance(geometry, Circle):
            return self._tessellate_circle(geometry)
        if isinstance(geometry, Ellipse):
            return self._tessellate_ellipse(geometry)
        if isinstance(geometry, dict) and geometry.get("type") == "line":
            return self._tessellate_line(geometry)
        if isinstance(geometry, dict) and geometry.get("type") == "polyline":
            return self._tessellate_polyline(geometry["points"], geometry.get("closed", False))
        if isinstance(geometry, IRPath):
            return self._tessellate_path(geometry)
        raise NotImplementedError(f"Unsupported geometry type: {type(geometry)!r}")

    # -- internal helpers -------------------------------------------------

    def _tessellate_rectangle(self, rect: Rectangle) -> TessellationResult:
        x, y = rect.bounds.x, rect.bounds.y
        w, h = rect.bounds.width, rect.bounds.height
        contour = np.array(
            [
                [x, y],
                [x + w, y],
                [x + w, y + h],
                [x, y + h],
                [x, y],
            ],
            dtype=float,
        )
        area = self._polygon_area(contour)
        return TessellationResult(contours=[contour], winding_rule="nonzero", areas=[area], stroke_width=None)

    def _tessellate_circle(self, circle: Circle, segments: int = 32) -> TessellationResult:
        return self._tessellate_ellipse(
            Ellipse(center=circle.center, radius_x=circle.radius, radius_y=circle.radius),
            segments=segments,
        )

    def _tessellate_ellipse(self, ellipse: Ellipse, segments: int = 32) -> TessellationResult:
        cx, cy = ellipse.center.x, ellipse.center.y
        rx, ry = ellipse.radius_x, ellipse.radius_y
        angles = np.linspace(0.0, 2 * np.pi, num=max(segments, 3), endpoint=True)
        contour = np.column_stack((cx + rx * np.cos(angles), cy + ry * np.sin(angles)))
        if not np.allclose(contour[0], contour[-1]):
            contour = np.vstack([contour, contour[0]])
        area = self._polygon_area(contour)
        return TessellationResult(contours=[contour], winding_rule="nonzero", areas=[area], stroke_width=None)

    def _tessellate_polyline(self, points: Iterable[tuple[float, float]], closed: bool) -> TessellationResult:
        pts = list(points)
        if closed and pts and pts[0] != pts[-1]:
            pts.append(pts[0])
        contour = np.array(pts, dtype=float)
        area = self._polygon_area(contour)
        return TessellationResult(contours=[contour], winding_rule="nonzero", areas=[area], stroke_width=None)

    def _tessellate_line(self, data: dict[str, float]) -> TessellationResult:
        contour = np.array(
            [
                [data["x1"], data["y1"]],
                [data["x2"], data["y2"]],
            ],
            dtype=float,
        )
        return TessellationResult(contours=[contour], winding_rule="nonzero", areas=[0.0], stroke_width=None)

    def _tessellate_path(self, path: IRPath) -> TessellationResult:
        contours: list[np.ndarray] = []
        current: list[list[float]] = []
        last_end: Point | None = None
        for segment in path.segments:
            start = getattr(segment, "start", None)
            if start is not None and (last_end is None or not self._points_close(start, last_end)):
                if current:
                    if path.is_closed and current[0] != current[-1]:
                        current.append(current[0])
                    contours.append(np.array(current, dtype=float))
                    current = []
                current.append([start.x, start.y])

            if isinstance(segment, LineSegment):
                current.append([segment.end.x, segment.end.y])
            elif isinstance(segment, BezierSegment):
                for point in self._flatten_cubic(segment, steps=16)[1:]:
                    current.append([point.x, point.y])
            else:
                continue
            last_end = getattr(segment, "end", last_end)

        if current:
            if path.is_closed and current[0] != current[-1]:
                current.append(current[0])
            contours.append(np.array(current, dtype=float))

        areas = [self._polygon_area(contour) for contour in contours]
        return TessellationResult(contours=contours, winding_rule="nonzero", areas=areas, stroke_width=None)

    # ------------------------------------------------------------------

    def tessellate_stroke(self, geometry, stroke_width: float) -> TessellationResult:
        base = self.tessellate_geometry(geometry)
        base.stroke_width = stroke_width
        if stroke_width is None or stroke_width <= 0 or not base.contours:
            base.stroke_outline = None
            return base

        outlines = [self._offset_contour(contour, stroke_width / 2.0) for contour in base.contours]
        base.stroke_outline = outlines
        return base

    # ------------------------------------------------------------------

    @staticmethod
    def _polygon_area(points: np.ndarray) -> float:
        if len(points) < 3 or not np.allclose(points[0], points[-1]):
            return 0.0
        x = points[:, 0]
        y = points[:, 1]
        area = float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) * 0.5
        return area

    @staticmethod
    def _points_close(a: Point, b: Point, tolerance: float = 1e-6) -> bool:
        return abs(a.x - b.x) <= tolerance and abs(a.y - b.y) <= tolerance

    @staticmethod
    def _flatten_cubic(segment: BezierSegment, steps: int = 16) -> list[Point]:
        def _bezier_point(t: float) -> Point:
            mt = 1.0 - t
            x = (
                mt ** 3 * segment.start.x
                + 3 * mt ** 2 * t * segment.control1.x
                + 3 * mt * t ** 2 * segment.control2.x
                + t ** 3 * segment.end.x
            )
            y = (
                mt ** 3 * segment.start.y
                + 3 * mt ** 2 * t * segment.control1.y
                + 3 * mt * t ** 2 * segment.control2.y
                + t ** 3 * segment.end.y
            )
            return Point(x, y)

        points = [_bezier_point(i / float(steps)) for i in range(steps + 1)]
        deduped: list[Point] = []
        for point in points:
            if not deduped or not Tessellator._points_close(point, deduped[-1]):
                deduped.append(point)
        return deduped

    def _offset_contour(self, contour: np.ndarray, offset: float) -> np.ndarray:
        if len(contour) < 2:
            return contour.copy()
        closed = self._points_close(Point(*contour[0]), Point(*contour[-1]))
        outline = []
        length = len(contour)
        for idx in range(length):
            prev_idx = idx - 1 if idx > 0 else (length - 2 if closed else 0)
            next_idx = idx + 1 if idx + 1 < length else (1 if closed else length - 1)
            prev_point = contour[prev_idx]
            next_point = contour[next_idx]
            vx = next_point[0] - prev_point[0]
            vy = next_point[1] - prev_point[1]
            length_vec = (vx ** 2 + vy ** 2) ** 0.5
            if length_vec == 0:
                outline.append(contour[idx].tolist())
                continue
            nx = -vy / length_vec
            ny = vx / length_vec
            outline.append([contour[idx][0] + nx * offset, contour[idx][1] + ny * offset])
        return np.array(outline, dtype=float)


__all__ = ["TessellationResult", "Tessellator"]
