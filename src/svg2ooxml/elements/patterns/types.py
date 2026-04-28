"""Shared pattern processor types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from lxml import etree as ET


class PatternComplexity(Enum):
    """Pattern complexity levels."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    UNSUPPORTED = "unsupported"


class PatternType(Enum):
    """Pattern type classification."""

    DOTS = "dots"
    LINES = "lines"
    DIAGONAL = "diagonal"
    GRID = "grid"
    CROSS = "cross"
    CUSTOM = "custom"
    UNSUPPORTED = "unsupported"


class PatternOptimization(Enum):
    """Pattern optimization strategies."""

    PRESET_MAPPING = "preset_mapping"
    COLOR_SIMPLIFICATION = "color_simplification"
    COLOR_SPACE_OPTIMIZATION = "color_space_optimization"
    TRANSFORM_FLATTENING = "transform_flattening"
    EMF_OPTIMIZATION = "emf_optimization"
    TILE_OPTIMIZATION = "tile_optimization"


@dataclass
class PatternGeometry:
    """Pattern geometric properties."""

    tile_width: float
    tile_height: float
    aspect_ratio: float
    units: str
    transform_matrix: list[float] | None
    content_units: str


@dataclass
class PatternAnalysis:
    """Result of pattern analysis."""

    element: ET.Element
    pattern_type: PatternType
    complexity: PatternComplexity
    geometry: PatternGeometry
    has_transforms: bool
    child_count: int
    colors_used: list[str]
    color_statistics: dict[str, Any] | None
    powerpoint_compatible: bool
    preset_candidate: str | None
    optimization_opportunities: list[PatternOptimization]
    estimated_performance_impact: str
    requires_preprocessing: bool
    emf_fallback_recommended: bool


__all__ = [
    "PatternAnalysis",
    "PatternComplexity",
    "PatternGeometry",
    "PatternOptimization",
    "PatternType",
]
