"""Shared types for curve text positioning."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from svg2ooxml.ir.geometry import Point


class PathSamplingMethod(Enum):
    """Path sampling methods for different use cases."""

    UNIFORM = "uniform"
    ARC_LENGTH = "arc_length"
    ADAPTIVE = "adaptive"
    DETERMINISTIC = "deterministic"


@dataclass
class PathSegment:
    """Represents a single path segment."""

    start_point: Point
    end_point: Point
    control_points: list[Point]
    segment_type: str
    length: float


__all__ = ["PathSamplingMethod", "PathSegment"]
