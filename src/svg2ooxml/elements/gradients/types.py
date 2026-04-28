"""Shared gradient processor types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from lxml import etree as ET


class GradientComplexity(Enum):
    """Gradient complexity levels."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    UNSUPPORTED = "unsupported"


class GradientOptimization(Enum):
    """Gradient optimization strategies."""

    COLOR_SIMPLIFICATION = "color_simplification"
    STOP_REDUCTION = "stop_reduction"
    TRANSFORM_FLATTENING = "transform_flattening"
    COLOR_SPACE_OPTIMIZATION = "color_space_optimization"
    VECTORIZATION = "vectorization"


@dataclass
class GradientMetrics:
    """Gradient performance metrics."""

    stop_count: int
    color_complexity: float
    transform_complexity: float
    memory_usage: int
    processing_time: float


@dataclass
class GradientAnalysis:
    """Result of gradient analysis."""

    element: ET.Element
    gradient_type: str
    complexity: GradientComplexity
    stop_count: int
    has_transforms: bool
    uses_advanced_features: bool
    color_spaces_used: list[str]
    colors_used: list[str]
    color_statistics: dict[str, Any]
    optimization_opportunities: list[GradientOptimization]
    powerpoint_compatible: bool
    estimated_performance_impact: str
    metrics: GradientMetrics
    requires_preprocessing: bool


__all__ = [
    "GradientAnalysis",
    "GradientComplexity",
    "GradientMetrics",
    "GradientOptimization",
]
