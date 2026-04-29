"""Utilities for generating DrawingML custom geometry from clip primitives."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.common.geometry.paths import parse_path_data
from svg2ooxml.common.geometry.segments import (
    ellipse_segments as _ellipse_segments,
)
from svg2ooxml.common.geometry.segments import (
    line_segments_from_points,
    transform_segments,
)
from svg2ooxml.drawingml.generator import CustomGeometry, DrawingMLPathGenerator
from svg2ooxml.ir.geometry import LineSegment, Point, SegmentType

PrimitiveDict = Mapping[str, Any]
PrimitiveIterable = Iterable[PrimitiveDict]
SegmentList = list[SegmentType]


class CustGeomGenerationError(Exception):
    """Raised when custom geometry generation fails."""


class CustGeomGenerator:
    """Generate DrawingML custGeom XML from path segments or clip primitives."""

    def __init__(
        self,
        *,
        path_generator: DrawingMLPathGenerator | None = None,
        primitive_builder: PrimitiveSegmentBuilder | None = None,
    ) -> None:
        self._path_generator = path_generator or DrawingMLPathGenerator()
        self._primitive_builder = primitive_builder or PrimitiveSegmentBuilder()

    def generate_from_segments(
        self,
        segments: Iterable[SegmentType],
        *,
        fill_mode: str = "none",
        stroke_mode: str = "none",
        closed: bool = True,
    ) -> CustomGeometry:
        segment_list = list(segments)
        if not segment_list:
            raise CustGeomGenerationError("Custom geometry requires at least one segment")
        return self._path_generator.generate_custom_geometry(
            segment_list,
            fill_mode=fill_mode,
            stroke_mode=stroke_mode,
            closed=closed,
        )

    def generate_from_primitives(
        self,
        primitives: PrimitiveIterable,
        *,
        fill_mode: str = "none",
        stroke_mode: str = "none",
        closed: bool = True,
    ) -> CustomGeometry:
        segments = self._primitive_builder.build(primitives)
        if not segments:
            raise CustGeomGenerationError("Unsupported or empty clip primitives")
        return self.generate_from_segments(
            segments,
            fill_mode=fill_mode,
            stroke_mode=stroke_mode,
            closed=closed,
        )


class PrimitiveSegmentBuilder:
    """Convert SVG clip primitives into IR path segments."""

    PrimitiveHandler = Callable[[PrimitiveDict, Matrix2D], SegmentList]

    def __init__(self) -> None:
        self._handlers: dict[str, PrimitiveSegmentBuilder.PrimitiveHandler] = {
            "rect": self._rect_segments,
            "circle": self._ellipse_segments,
            "ellipse": self._ellipse_segments,
            "line": self._line_segments,
            "polygon": self._polygon_segments,
            "polyline": self._polyline_segments,
            "path": self._path_segments,
        }

    def build(self, primitives: PrimitiveIterable) -> SegmentList:
        segments: SegmentList = []
        for primitive in primitives or ():
            primitive_type = primitive.get("type")
            if not primitive_type:
                continue
            handler = self._handlers.get(primitive_type)
            if handler is None:
                continue
            matrix = self._matrix_from_tuple(primitive.get("transform"))
            segments.extend(handler(primitive, matrix))
        return segments

    def _rect_segments(self, primitive: PrimitiveDict, matrix: Matrix2D) -> SegmentList:
        x = float(primitive.get("x", 0.0) or 0.0)
        y = float(primitive.get("y", 0.0) or 0.0)
        width = float(primitive.get("width", 0.0) or 0.0)
        height = float(primitive.get("height", 0.0) or 0.0)
        if width <= 0 or height <= 0:
            return []

        corners = [
            Point(x, y),
            Point(x + width, y),
            Point(x + width, y + height),
            Point(x, y + height),
        ]
        transformed = [matrix.transform_point(point) for point in corners]
        transformed.append(transformed[0])
        return list(line_segments_from_points(transformed))

    def _ellipse_segments(self, primitive: PrimitiveDict, matrix: Matrix2D) -> SegmentList:
        cx = float(primitive.get("cx", primitive.get("x", 0.0)) or 0.0)
        cy = float(primitive.get("cy", primitive.get("y", 0.0)) or 0.0)
        rx = float(primitive.get("r", primitive.get("rx", 0.0)) or 0.0)
        ry = float(primitive.get("r", primitive.get("ry", rx)) or 0.0)
        return apply_matrix_to_segments(_ellipse_segments(cx, cy, rx, ry), matrix)

    def _line_segments(self, primitive: PrimitiveDict, matrix: Matrix2D) -> SegmentList:
        x1 = float(primitive.get("x1", 0.0) or 0.0)
        y1 = float(primitive.get("y1", 0.0) or 0.0)
        x2 = float(primitive.get("x2", 0.0) or 0.0)
        y2 = float(primitive.get("y2", 0.0) or 0.0)
        start = matrix.transform_point(Point(x1, y1))
        end = matrix.transform_point(Point(x2, y2))
        return [LineSegment(start, end)]

    def _polygon_segments(self, primitive: PrimitiveDict, matrix: Matrix2D) -> SegmentList:
        points = self._parse_points(primitive.get("points"))
        if not points:
            return []
        points.append(points[0])
        return self._points_to_segments(points, matrix)

    def _polyline_segments(self, primitive: PrimitiveDict, matrix: Matrix2D) -> SegmentList:
        points = self._parse_points(primitive.get("points"))
        if len(points) < 2:
            return []
        return self._points_to_segments(points, matrix)

    def _path_segments(self, primitive: PrimitiveDict, matrix: Matrix2D) -> SegmentList:
        path_data = primitive.get("d")
        if not path_data:
            return []
        try:
            parsed_segments = list(parse_path_data(path_data))
        except Exception:  # pragma: no cover - parser guarantees raise
            return []
        return apply_matrix_to_segments(parsed_segments, matrix)

    def _points_to_segments(self, points: Sequence[tuple[float, float]], matrix: Matrix2D) -> SegmentList:
        transformed = [matrix.transform_point(Point(px, py)) for px, py in points]
        return list(line_segments_from_points(transformed))

    @staticmethod
    def _matrix_from_tuple(values: Any) -> Matrix2D:
        if not values:
            return Matrix2D.identity()
        try:
            return Matrix2D(*values)
        except TypeError:
            return Matrix2D.identity()

    @staticmethod
    def _parse_points(value: str | None) -> list[tuple[float, float]]:
        if not value:
            return []
        cleaned = value.replace(",", " ")
        parts = cleaned.split()
        if len(parts) % 2 != 0:
            parts = parts[:-1]
        result: list[tuple[float, float]] = []
        it = iter(parts)
        for x_str, y_str in zip(it, it, strict=False):
            try:
                result.append((float(x_str), float(y_str)))
            except ValueError:
                continue
        return result


def apply_matrix_to_segments(segments: Iterable[SegmentType], matrix: Matrix2D) -> SegmentList:
    return transform_segments(segments, matrix.transform_point)


_DEFAULT_PRIMITIVE_BUILDER = PrimitiveSegmentBuilder()


def segments_from_primitives(primitives: PrimitiveIterable) -> SegmentList:
    """Public helper mirroring PrimitiveSegmentBuilder.build()."""

    return _DEFAULT_PRIMITIVE_BUILDER.build(primitives)


__all__ = [
    "CustGeomGenerationError",
    "CustGeomGenerator",
    "PrimitiveSegmentBuilder",
    "apply_matrix_to_segments",
    "segments_from_primitives",
]
