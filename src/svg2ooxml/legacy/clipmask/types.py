"""Shared clip and mask data structures for svg2ooxml."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from svg2ooxml.ir.geometry import Rect, SegmentType
from svg2ooxml.common.geometry import Matrix2D


@dataclass(slots=True)
class ClipDefinition:
    """Normalized clipPath definition derived from SVG content."""

    clip_id: str
    segments: tuple[SegmentType, ...]
    bounding_box: Rect
    clip_rule: str | None
    transform: Matrix2D | None
    primitives: tuple[dict[str, Any], ...] = ()


@dataclass(slots=True)
class MaskInfo:
    """Normalized mask definition capturing geometry and metadata."""

    mask_id: str
    mask_type: str | None
    mode: str
    mask_units: str | None
    mask_content_units: str | None
    region: Rect | None
    opacity: float | None
    transform: Matrix2D | None
    children: tuple[str, ...]
    bounding_box: Rect | None = None
    segments: tuple[SegmentType, ...] = ()
    content_xml: tuple[str, ...] = ()
    primitives: tuple[dict[str, Any], ...] = ()
    raw_region: dict[str, Any] = field(default_factory=dict)
    policy_hints: dict[str, Any] = field(default_factory=dict)


__all__ = ["ClipDefinition", "MaskInfo"]
