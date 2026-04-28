"""Transform helpers for ``ResvgShapeAdapter``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from svg2ooxml.common.geometry.segments import transform_segments
from svg2ooxml.core.resvg.geometry.matrix_bridge import (
    IDENTITY_MATRIX_TUPLE,
    matrix_to_tuple,
    transform_point,
)
from svg2ooxml.ir.geometry import Point, SegmentType

if TYPE_CHECKING:
    from svg2ooxml.core.resvg.usvg_tree import BaseNode


class ResvgShapeTransformMixin:
    """Apply resvg transforms to IR segments."""

    def _apply_node_transform(
        self,
        segments: list[SegmentType],
        node: BaseNode,
    ) -> list[SegmentType]:
        matrix = node.transform
        if matrix is None or self._is_identity(matrix):
            return segments
        return self._apply_transform_to_segments(segments, matrix)

    def _is_identity(self, matrix) -> bool:
        """Return True when *matrix* has no transform effect."""
        values = matrix_to_tuple(matrix)
        return all(
            abs(value - expected) < 1e-9
            for value, expected in zip(values, IDENTITY_MATRIX_TUPLE, strict=True)
        )

    def _apply_transform_to_point(self, point: Point, matrix) -> Point:
        """Apply a resvg Matrix transform to a point."""
        return transform_point(point, matrix)

    def _apply_transform_to_segments(
        self, segments: list[SegmentType], matrix
    ) -> list[SegmentType]:
        """Apply a resvg Matrix transform to all segments."""
        return transform_segments(
            segments,
            lambda point: self._apply_transform_to_point(point, matrix),
        )


__all__ = ["ResvgShapeTransformMixin"]
