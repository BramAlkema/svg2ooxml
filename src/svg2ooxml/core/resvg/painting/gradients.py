"""Gradient and pattern data structures mirroring usvg paint servers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ..geometry.matrix import Matrix
from .paint import Color


@dataclass(slots=True)
class GradientStop:
    offset: float
    color: Color


@dataclass(slots=True)
class LinearGradient:
    x1: float
    y1: float
    x2: float
    y2: float
    units: str
    spread_method: str
    transform: Matrix
    stops: Tuple[GradientStop, ...]
    href: Optional[str] = None
    specified: Tuple[str, ...] = ()


@dataclass(slots=True)
class RadialGradient:
    cx: float
    cy: float
    r: float
    fx: float
    fy: float
    units: str
    spread_method: str
    transform: Matrix
    stops: Tuple[GradientStop, ...]
    href: Optional[str] = None
    specified: Tuple[str, ...] = ()


@dataclass(slots=True)
class PatternPaint:
    x: float
    y: float
    width: float
    height: float
    units: str
    content_units: str
    transform: Matrix
    href: Optional[str] = None
    specified: Tuple[str, ...] = ()
