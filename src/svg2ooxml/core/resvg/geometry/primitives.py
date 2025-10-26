"""Basic geometric primitives used by the render pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MoveTo:
    x: float
    y: float


@dataclass(frozen=True)
class LineTo:
    x: float
    y: float


@dataclass(frozen=True)
class ClosePath:
    pass


@dataclass(frozen=True)
class CubicCurve:
    p1x: float
    p1y: float
    p2x: float
    p2y: float
    x: float
    y: float


@dataclass(frozen=True)
class QuadraticCurve:
    px: float
    py: float
    x: float
    y: float


@dataclass(frozen=True)
class Arc:
    rx: float
    ry: float
    x_axis_rotation: float
    large_arc: bool
    sweep: bool
    x: float
    y: float
