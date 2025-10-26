"""Native shape representations for svg2ooxml IR."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .effects import Effect
from .geometry import Point, Rect
from .paint import Paint, Stroke


@dataclass
class Circle:
    center: Point
    radius: float
    fill: Paint = None
    stroke: Stroke | None = None
    opacity: float = 1.0
    effects: list[Effect] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)
    element_id: str | None = None

    def __post_init__(self) -> None:
        if self.radius <= 0:
            raise ValueError("radius must be positive")
        if not (0.0 <= self.opacity <= 1.0):
            raise ValueError("opacity must be 0.0‐1.0")

    @property
    def bbox(self) -> Rect:
        return Rect(
            x=self.center.x - self.radius,
            y=self.center.y - self.radius,
            width=self.radius * 2.0,
            height=self.radius * 2.0,
        )

    @property
    def is_closed(self) -> bool:
        return True


@dataclass
class Ellipse:
    center: Point
    radius_x: float
    radius_y: float
    fill: Paint = None
    stroke: Stroke | None = None
    opacity: float = 1.0
    effects: list[Effect] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)
    element_id: str | None = None

    def __post_init__(self) -> None:
        if self.radius_x <= 0 or self.radius_y <= 0:
            raise ValueError("ellipse radii must be positive")
        if not (0.0 <= self.opacity <= 1.0):
            raise ValueError("opacity must be 0.0‐1.0")

    @property
    def bbox(self) -> Rect:
        return Rect(
            x=self.center.x - self.radius_x,
            y=self.center.y - self.radius_y,
            width=self.radius_x * 2.0,
            height=self.radius_y * 2.0,
        )

    @property
    def is_closed(self) -> bool:
        return True

    def is_circle(self, tolerance: float = 0.01) -> bool:
        if self.radius_x == 0 or self.radius_y == 0:
            return False
        ratio = self.radius_x / self.radius_y
        return abs(ratio - 1.0) < tolerance


@dataclass
class Rectangle:
    bounds: Rect
    fill: Paint = None
    stroke: Stroke | None = None
    opacity: float = 1.0
    corner_radius: float = 0.0
    effects: list[Effect] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)
    element_id: str | None = None

    def __post_init__(self) -> None:
        if self.bounds.width <= 0 or self.bounds.height <= 0:
            raise ValueError("rectangle bounds must be positive")
        if self.corner_radius < 0:
            raise ValueError("corner radius must be non-negative")
        if not (0.0 <= self.opacity <= 1.0):
            raise ValueError("opacity must be 0.0‐1.0")

    @property
    def bbox(self) -> Rect:
        return self.bounds

    @property
    def is_closed(self) -> bool:
        return True

    @property
    def is_rounded(self) -> bool:
        return self.corner_radius > 0


@dataclass
class Line:
    start: Point
    end: Point
    stroke: Stroke | None = None
    opacity: float = 1.0
    effects: list[Effect] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)
    element_id: str | None = None

    def __post_init__(self) -> None:
        if not (0.0 <= self.opacity <= 1.0):
            raise ValueError("opacity must be 0.0‐1.0")

    @property
    def bbox(self) -> Rect:
        min_x = min(self.start.x, self.end.x)
        min_y = min(self.start.y, self.end.y)
        max_x = max(self.start.x, self.end.x)
        max_y = max(self.start.y, self.end.y)
        return Rect(min_x, min_y, max_x - min_x, max_y - min_y)

    @property
    def is_degenerate(self) -> bool:
        return self.start.x == self.end.x and self.start.y == self.end.y


@dataclass
class Polyline:
    points: list[Point]
    fill: Paint = None
    stroke: Stroke | None = None
    opacity: float = 1.0
    effects: list[Effect] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)
    element_id: str | None = None

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("polyline requires at least two points")
        if not (0.0 <= self.opacity <= 1.0):
            raise ValueError("opacity must be 0.0‐1.0")

    @property
    def bbox(self) -> Rect:
        xs = [point.x for point in self.points]
        ys = [point.y for point in self.points]
        min_x = min(xs)
        min_y = min(ys)
        max_x = max(xs)
        max_y = max(ys)
        return Rect(min_x, min_y, max_x - min_x, max_y - min_y)

    @property
    def is_closed(self) -> bool:
        return False


@dataclass
class Polygon:
    points: list[Point]
    fill: Paint = None
    stroke: Stroke | None = None
    opacity: float = 1.0
    effects: list[Effect] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)
    element_id: str | None = None

    def __post_init__(self) -> None:
        if len(self.points) < 3:
            raise ValueError("polygon requires at least three points")
        if not (0.0 <= self.opacity <= 1.0):
            raise ValueError("opacity must be 0.0‐1.0")

    @property
    def bbox(self) -> Rect:
        xs = [point.x for point in self.points]
        ys = [point.y for point in self.points]
        min_x = min(xs)
        min_y = min(ys)
        max_x = max(xs)
        max_y = max(ys)
        return Rect(min_x, min_y, max_x - min_x, max_y - min_y)

    @property
    def is_closed(self) -> bool:
        return True


__all__ = ["Circle", "Ellipse", "Rectangle", "Line", "Polyline", "Polygon"]
