"""Convert SVG path data into IR segments with optional transforms."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Callable, Sequence

from svg2ooxml.geometry.paths.parser import PathParseError, parse_path_data
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType
from svg2ooxml.parser.geometry import Matrix2D


class PathSegmentConverter:
    """Lightweight bridge between SVG path data and IR geometry segments."""

    def __init__(self, logger: Callable[[str], None] | None = None) -> None:
        self._log = logger

    def convert(self, path_data: str, coord_space_or_matrix: object | None = None) -> list[SegmentType]:
        """Parse ``path_data`` and optionally transform the resulting segments."""
        if not path_data or not path_data.strip():
            return []
        try:
            segments = list(parse_path_data(path_data))
        except PathParseError as exc:
            if self._log:
                self._log(f"Path parse error: {exc}")
            return []

        if coord_space_or_matrix is None:
            return segments
        return self._apply_transform(segments, coord_space_or_matrix)

    def _apply_transform(
        self,
        segments: Sequence[SegmentType],
        coord_space_or_matrix: object,
    ) -> list[SegmentType]:
        if hasattr(coord_space_or_matrix, "apply_segments"):
            try:
                return list(coord_space_or_matrix.apply_segments(list(segments)))  # type: ignore[misc]
            except Exception:
                pass

        matrix = self._extract_matrix(coord_space_or_matrix)
        if matrix is None:
            return list(segments)
        return _transform_segments(segments, matrix)

    def _extract_matrix(self, obj: object) -> Matrix2D | None:
        if isinstance(obj, Matrix2D):
            return obj
        if hasattr(obj, "current"):
            candidate = getattr(obj, "current")
            if isinstance(candidate, Matrix2D):
                return candidate
        if hasattr(obj, "transform_point"):
            return obj  # type: ignore[return-value]
        return None


def _transform_segments(segments: Iterable[SegmentType], matrix: object) -> list[SegmentType]:
    transformed: list[SegmentType] = []
    for segment in segments:
        if isinstance(segment, LineSegment):
            transformed.append(
                LineSegment(
                    start=_transform_point(matrix, segment.start),
                    end=_transform_point(matrix, segment.end),
                )
            )
        elif isinstance(segment, BezierSegment):
            transformed.append(
                BezierSegment(
                    start=_transform_point(matrix, segment.start),
                    control1=_transform_point(matrix, segment.control1),
                    control2=_transform_point(matrix, segment.control2),
                    end=_transform_point(matrix, segment.end),
                )
            )
        else:
            transformed.append(segment)
    return transformed


def _transform_point(matrix: object, point: Point) -> Point:
    if hasattr(matrix, "transform_point"):
        return matrix.transform_point(point)
    # Fallback: assume matrix is callable returning tuple
    result = matrix(point)  # type: ignore[operator]
    return Point(float(result[0]), float(result[1]))


__all__ = ["PathSegmentConverter"]
