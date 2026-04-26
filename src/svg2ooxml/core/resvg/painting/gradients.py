"""Gradient and pattern data structures mirroring usvg paint servers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from svg2ooxml.common.units.conversion import ConversionContext

from svg2ooxml.core.resvg.geometry.matrix import Matrix
from svg2ooxml.core.resvg.painting.paint import Color


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
    stops: tuple[GradientStop, ...]
    href: str | None = None
    specified: tuple[str, ...] = ()
    raw_attributes: dict[str, str] = field(default_factory=dict)
    context: ConversionContext | None = None


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
    stops: tuple[GradientStop, ...]
    href: str | None = None
    specified: tuple[str, ...] = ()
    raw_attributes: dict[str, str] = field(default_factory=dict)
    context: ConversionContext | None = None


@dataclass(slots=True)
class PatternPaint:
    x: float
    y: float
    width: float
    height: float
    units: str
    content_units: str
    transform: Matrix
    href: str | None = None
    specified: tuple[str, ...] = ()
