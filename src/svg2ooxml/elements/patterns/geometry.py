"""Geometry analysis and optimization detection for patterns."""

from __future__ import annotations

import logging
import math
from typing import Any

from lxml import etree as ET

from svg2ooxml.common.geometry import parse_transform_list
from svg2ooxml.common.units.lengths import (
    parse_number,
    parse_number_or_percent,
    resolve_length_px,
)

logger = logging.getLogger(__name__)


def extract_pattern_geometry(element: ET.Element) -> Any:
    """Extract pattern geometric properties.

    Returns a ``PatternGeometry``-compatible tuple of values.  The caller
    is responsible for constructing the dataclass instance (to avoid
    importing the coordinator).
    """
    width_str = element.get("width", "10")
    height_str = element.get("height", "10")

    width = parse_dimension(width_str)
    height = parse_dimension(height_str)

    aspect_ratio = width / height if height != 0 else 1.0

    units = element.get("patternUnits", "objectBoundingBox")
    content_units = element.get("patternContentUnits", "userSpaceOnUse")
    transform_str = element.get("patternTransform", "")

    transform_matrix = None
    if transform_str:
        transform_matrix = parse_transform_matrix(transform_str)

    return {
        "tile_width": width,
        "tile_height": height,
        "aspect_ratio": aspect_ratio,
        "units": units,
        "transform_matrix": transform_matrix,
        "content_units": content_units,
    }


def parse_dimension(dim_str: str) -> float:
    """Parse dimension string to float value."""
    fraction = parse_number_or_percent(dim_str, math.nan)
    if fraction == fraction:
        return fraction
    return resolve_length_px(dim_str, None, axis="x", default=10.0)


def parse_transform_matrix(transform_str: str) -> list[float] | None:
    """Parse transform string to matrix values."""
    try:
        return list(parse_transform_list(transform_str).as_tuple())

    except Exception as e:
        logger.warning(f"Failed to parse transform: {e}")

    return None


def identify_pattern_optimizations(
    element: ET.Element,
    pattern_type: Any,
    complexity: Any,
    has_transforms: bool,
    geometry: Any,
    color_summary: dict[str, object],
    PatternType: type,
    PatternComplexity: type,
    PatternOptimization: type,
) -> list[Any]:
    """Identify optimization opportunities."""
    optimizations = []

    if pattern_type in [PatternType.DOTS, PatternType.LINES, PatternType.DIAGONAL]:
        optimizations.append(PatternOptimization.PRESET_MAPPING)

    hue_spread = color_summary.get("hue_spread")
    unique_count = color_summary.get("unique", 0)

    if isinstance(hue_spread, (int, float)):
        if hue_spread < 35 and unique_count > 2:
            optimizations.append(PatternOptimization.COLOR_SIMPLIFICATION)
    elif unique_count and unique_count > 2:
        optimizations.append(PatternOptimization.COLOR_SIMPLIFICATION)

    recommended_space = color_summary.get("recommended_space")
    complexity_score = parse_number(color_summary.get("complexity"), 0.0)
    if recommended_space and recommended_space != "srgb":
        optimizations.append(PatternOptimization.COLOR_SPACE_OPTIMIZATION)
    elif complexity_score > 0.6:
        optimizations.append(PatternOptimization.COLOR_SPACE_OPTIMIZATION)

    if has_transforms:
        optimizations.append(PatternOptimization.TRANSFORM_FLATTENING)

    if complexity in [PatternComplexity.MODERATE, PatternComplexity.COMPLEX]:
        optimizations.append(PatternOptimization.EMF_OPTIMIZATION)

    if geometry.tile_width > 100 or geometry.tile_height > 100:
        optimizations.append(PatternOptimization.TILE_OPTIMIZATION)

    return optimizations


def estimate_performance_impact(
    complexity: Any,
    child_count: int,
    geometry: Any,
    color_summary: dict[str, object],
    PatternComplexity: type,
) -> str:
    """Estimate performance impact."""
    color_complexity = parse_number(color_summary.get("complexity"), 0.0)

    if (
        complexity == PatternComplexity.SIMPLE
        and child_count <= 3
        and color_complexity < 0.4
    ):
        return "low"
    elif (
        complexity == PatternComplexity.MODERATE
        or child_count <= 8
        or color_complexity < 0.75
    ):
        return "medium"
    elif (
        complexity == PatternComplexity.COMPLEX
        or child_count > 15
        or color_complexity >= 0.75
    ):
        return "high"
    else:
        return "very_high"


def requires_preprocessing(
    element: ET.Element,
    pattern_type: Any,
    optimizations: list[Any],
    PatternOptimization: type,
) -> bool:
    """Check if pattern would benefit from preprocessing."""
    if element.get("data-pattern-optimized"):
        return False

    if PatternOptimization.TRANSFORM_FLATTENING in optimizations:
        return True

    if PatternOptimization.COLOR_SIMPLIFICATION in optimizations:
        return True

    if PatternOptimization.TILE_OPTIMIZATION in optimizations:
        return True

    return False


def should_use_emf_fallback(
    pattern_type: Any,
    complexity: Any,
    has_transforms: bool,
    preset_candidate: str | None,
    PatternComplexity: type,
    PatternType: type,
) -> bool:
    """Determine if EMF fallback is recommended."""
    if complexity in [PatternComplexity.COMPLEX, PatternComplexity.UNSUPPORTED]:
        return True

    if pattern_type == PatternType.CUSTOM and not preset_candidate:
        return True

    if has_transforms and complexity != PatternComplexity.SIMPLE:
        return True

    return False


def is_translation_only(transform_matrix: list[float]) -> bool:
    """Return True when the matrix represents a pure translation."""
    if len(transform_matrix) != 6:
        return False
    a, b, c, d, _tx, _ty = transform_matrix
    return (
        abs(a - 1.0) < 1e-9
        and abs(d - 1.0) < 1e-9
        and abs(b) < 1e-9
        and abs(c) < 1e-9
    )
