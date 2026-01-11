"""Coordinate space utilities used during IR conversion."""

from __future__ import annotations

from dataclasses import dataclass, field

from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType
from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.common.geometry.transforms.space import CoordinateSpace as TransformSpace


@dataclass
class CoordinateSpace:
    """Maintain a CTM stack and expose helpers for coordinate transforms."""

    _space: TransformSpace = field(default_factory=TransformSpace)

    def push(self, transform: Matrix2D | None) -> None:
        """Compose the provided transform with the current CTM."""
        if transform is None:
            self._space.push(None)
        else:
            self._space.push(transform)

    def pop(self) -> None:
        """Pop the latest CTM, leaving the viewport matrix intact."""
        self._space.pop()

    @property
    def current(self) -> Matrix2D:
        return self._space.current

    def apply_point(self, x: float, y: float) -> tuple[float, float]:
        return self._space.apply_point(x, y)

    def apply_point_obj(self, point: Point) -> Point:
        x, y = self.apply_point(point.x, point.y)
        return Point(x, y)

    def apply_segments(self, segments: list[SegmentType]) -> list[SegmentType]:
        transformed: list[SegmentType] = []
        for segment in segments:
            if isinstance(segment, LineSegment):
                transformed.append(
                    LineSegment(
                        start=self.apply_point_obj(segment.start),
                        end=self.apply_point_obj(segment.end),
                    )
                )
            elif isinstance(segment, BezierSegment):
                transformed.append(
                    BezierSegment(
                        start=self.apply_point_obj(segment.start),
                        control1=self.apply_point_obj(segment.control1),
                        control2=self.apply_point_obj(segment.control2),
                        end=self.apply_point_obj(segment.end),
                    )
                )
            else:
                transformed.append(segment)
        return transformed
