"""Descriptor types for resvg paint bridge data."""

from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree

from svg2ooxml.core.resvg.geometry.matrix_bridge import MatrixTuple


@dataclass(slots=True)
class GradientStopDescriptor:
    offset: float
    color: str
    opacity: float


@dataclass(slots=True)
class LinearGradientDescriptor:
    gradient_id: str | None
    x1: float
    y1: float
    x2: float
    y2: float
    units: str
    spread_method: str
    transform: MatrixTuple
    stops: tuple[GradientStopDescriptor, ...]
    href: str | None = None
    specified: tuple[str, ...] = ("x1", "y1", "x2", "y2")
    raw_attributes: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class RadialGradientDescriptor:
    gradient_id: str | None
    cx: float
    cy: float
    r: float
    fx: float
    fy: float
    units: str
    spread_method: str
    transform: MatrixTuple
    stops: tuple[GradientStopDescriptor, ...]
    href: str | None = None
    specified: tuple[str, ...] = ("cx", "cy", "r", "fx", "fy")
    raw_attributes: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class MeshGradientDescriptor:
    gradient_id: str | None
    rows: int
    columns: int
    patch_count: int
    stop_count: int
    colors: tuple[str, ...]
    attributes: dict[str, str]
    element: etree._Element
    href: str | None = None


GradientDescriptor = LinearGradientDescriptor | RadialGradientDescriptor | MeshGradientDescriptor


@dataclass(slots=True)
class PatternDescriptor:
    pattern_id: str | None
    x: float
    y: float
    width: float
    height: float
    units: str
    content_units: str
    transform: MatrixTuple
    href: str | None
    attributes: dict[str, str]
    children: tuple[etree._Element, ...]


__all__ = [
    "GradientDescriptor",
    "GradientStopDescriptor",
    "LinearGradientDescriptor",
    "RadialGradientDescriptor",
    "MeshGradientDescriptor",
    "PatternDescriptor",
]
