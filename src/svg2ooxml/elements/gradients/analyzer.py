"""Gradient analysis helpers for the element processor."""

from __future__ import annotations

import re
from typing import Any

from lxml import etree as ET

from svg2ooxml.color import summarize_palette
from svg2ooxml.common.gradient_units import parse_gradient_offset
from svg2ooxml.elements.gradients.types import (
    GradientAnalysis,
    GradientComplexity,
    GradientMetrics,
    GradientOptimization,
)


def perform_gradient_analysis(
    element: ET.Element,
    context: Any,
    complexity_thresholds: dict[str, int],
) -> GradientAnalysis:
    """Perform detailed gradient analysis."""
    _ = context
    tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
    gradient_type = tag if tag in ["linearGradient", "radialGradient"] else "unknown"

    stop_analysis = analyze_gradient_stops(element)
    transform_analysis = analyze_gradient_transforms(element)
    advanced_features = check_advanced_features(element)
    complexity = assess_gradient_complexity(
        stop_analysis["count"],
        transform_analysis["complexity"],
        advanced_features,
        complexity_thresholds,
    )
    optimizations = identify_gradient_optimizations(
        element,
        stop_analysis,
        transform_analysis,
        advanced_features,
        complexity_thresholds,
    )
    powerpoint_compatible = assess_powerpoint_compatibility(
        gradient_type, complexity, advanced_features
    )
    metrics = calculate_gradient_metrics(element, stop_analysis, transform_analysis)
    performance_impact = estimate_performance_impact(metrics, complexity)
    requires_preproc = requires_preprocessing(
        element, transform_analysis, optimizations
    )

    return GradientAnalysis(
        element=element,
        gradient_type=gradient_type,
        complexity=complexity,
        stop_count=stop_analysis["count"],
        has_transforms=transform_analysis["has_transforms"],
        uses_advanced_features=advanced_features,
        color_spaces_used=stop_analysis["color_spaces"],
        colors_used=stop_analysis["colors_used"],
        color_statistics=stop_analysis["color_statistics"],
        optimization_opportunities=optimizations,
        powerpoint_compatible=powerpoint_compatible,
        estimated_performance_impact=performance_impact,
        metrics=metrics,
        requires_preprocessing=requires_preproc,
    )


def analyze_gradient_stops(element: ET.Element) -> dict[str, Any]:
    """Analyze gradient stops for optimization opportunities."""
    stop_elements = element.findall(".//stop")
    if not stop_elements:
        stop_elements = element.findall(".//{http://www.w3.org/2000/svg}stop")

    stop_count = len(stop_elements)
    colors_raw: list[str] = []
    color_spaces = set()
    positions = []

    for stop in stop_elements:
        offset_str = stop.get("offset", "0")
        positions.append(parse_gradient_offset(offset_str))

        color_str = stop.get("stop-color", "#000000")
        colors_raw.append(color_str)
        lower = color_str.strip().lower()
        if lower.startswith("#"):
            color_spaces.add("hex")
        elif lower.startswith("rgb(") or lower.startswith("rgba("):
            color_spaces.add("rgb")
        elif lower.startswith("hsl(") or lower.startswith("hsla("):
            color_spaces.add("hsl")
        else:
            color_spaces.add("named")

    palette_summary = summarize_palette(colors_raw)
    unique_colors = palette_summary["unique"]
    color_complexity = palette_summary["complexity"]
    recommended_space = palette_summary.get("recommended_space", "srgb")

    if palette_summary.get("advanced_available"):
        color_spaces.update({"oklab", "oklch"})
    if recommended_space:
        color_spaces.add(recommended_space)

    if len(positions) > 1:
        positions.sort()
        spacings = [
            positions[i + 1] - positions[i] for i in range(len(positions) - 1)
        ]
        avg_spacing = sum(spacings) / len(spacings)
        spacing_variance = sum((s - avg_spacing) ** 2 for s in spacings) / len(
            spacings
        )
        irregular_spacing = spacing_variance > 0.01
    else:
        irregular_spacing = False

    return {
        "count": stop_count,
        "colors_used": palette_summary["palette"],
        "color_spaces": list(color_spaces),
        "unique_colors": unique_colors,
        "color_complexity": color_complexity,
        "positions": positions,
        "irregular_spacing": irregular_spacing,
        "color_statistics": palette_summary,
        "recommended_space": recommended_space,
        "advanced_available": palette_summary.get("advanced_available", False),
    }


def analyze_gradient_transforms(element: ET.Element) -> dict[str, Any]:
    """Analyze gradient transforms for optimization opportunities."""
    transform_str = element.get("gradientTransform", "")
    has_transforms = bool(transform_str.strip())

    if not has_transforms:
        return {
            "has_transforms": False,
            "complexity": 0.0,
            "transform_count": 0,
            "types": [],
        }

    transform_functions = re.findall(
        r"(matrix|translate|scale|rotate|skewX|skewY)\s*\([^)]+\)",
        transform_str,
    )
    transform_count = len(transform_functions)
    transform_types = [match.split("(")[0] for match in transform_functions]
    complexity_weights = {
        "translate": 0.2,
        "scale": 0.3,
        "rotate": 0.5,
        "matrix": 1.0,
        "skewX": 0.7,
        "skewY": 0.7,
    }
    complexity = sum(complexity_weights.get(t, 0.5) for t in transform_types)

    return {
        "has_transforms": True,
        "complexity": complexity,
        "transform_count": transform_count,
        "types": transform_types,
        "transform_string": transform_str,
    }


def check_advanced_features(element: ET.Element) -> bool:
    """Check for advanced gradient features that may impact compatibility."""
    advanced_attrs = [
        "gradientUnits",
        "spreadMethod",
        "href",
        "xlink:href",
    ]

    for attr in advanced_attrs:
        if element.get(attr):
            return True

    if len(list(element)) > 0:
        for child in element:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag not in ["stop"]:
                return True

    return False


def assess_gradient_complexity(
    stop_count: int,
    transform_complexity: float,
    advanced_features: bool,
    thresholds: dict[str, int],
) -> GradientComplexity:
    """Assess overall gradient complexity."""
    if stop_count <= thresholds["simple_stop_count"]:
        base_complexity = GradientComplexity.SIMPLE
    elif stop_count <= thresholds["moderate_stop_count"]:
        base_complexity = GradientComplexity.MODERATE
    elif stop_count <= thresholds["complex_stop_count"]:
        base_complexity = GradientComplexity.COMPLEX
    else:
        base_complexity = GradientComplexity.UNSUPPORTED

    if transform_complexity > 1.0:
        if base_complexity == GradientComplexity.SIMPLE:
            base_complexity = GradientComplexity.MODERATE
        elif base_complexity == GradientComplexity.MODERATE:
            base_complexity = GradientComplexity.COMPLEX

    if advanced_features:
        if base_complexity == GradientComplexity.SIMPLE:
            base_complexity = GradientComplexity.MODERATE
        elif base_complexity == GradientComplexity.MODERATE:
            base_complexity = GradientComplexity.COMPLEX

    return base_complexity


def identify_gradient_optimizations(
    element: ET.Element,
    stop_analysis: dict[str, Any],
    transform_analysis: dict[str, Any],
    advanced_features: bool,
    thresholds: dict[str, int],
) -> list[GradientOptimization]:
    """Identify optimization opportunities."""
    _ = element, advanced_features
    optimizations = []
    color_stats = stop_analysis.get("color_statistics", {}) or {}

    hue_spread = color_stats.get("hue_spread")
    if hue_spread is not None:
        if hue_spread < 30 and stop_analysis["count"] > 4:
            optimizations.append(GradientOptimization.COLOR_SIMPLIFICATION)
    elif stop_analysis["color_complexity"] > 0.8 and stop_analysis["count"] > 5:
        optimizations.append(GradientOptimization.COLOR_SIMPLIFICATION)

    if stop_analysis["count"] > thresholds["simple_stop_count"]:
        if stop_analysis["unique_colors"] < stop_analysis["count"] * 0.7:
            optimizations.append(GradientOptimization.STOP_REDUCTION)
        elif isinstance(hue_spread, (int, float)) and hue_spread < 15:
            optimizations.append(GradientOptimization.STOP_REDUCTION)

    if transform_analysis["has_transforms"] and transform_analysis["complexity"] > 0.5:
        optimizations.append(GradientOptimization.TRANSFORM_FLATTENING)

    recommended_space = stop_analysis.get("recommended_space")
    if recommended_space and recommended_space != "srgb":
        optimizations.append(GradientOptimization.COLOR_SPACE_OPTIMIZATION)
    elif len(stop_analysis["color_spaces"]) > 1:
        optimizations.append(GradientOptimization.COLOR_SPACE_OPTIMIZATION)

    if stop_analysis["count"] > 3 or transform_analysis["transform_count"] > 1:
        optimizations.append(GradientOptimization.VECTORIZATION)

    return optimizations


def assess_powerpoint_compatibility(
    gradient_type: str,
    complexity: GradientComplexity,
    advanced_features: bool,
) -> bool:
    """Assess PowerPoint compatibility."""
    if gradient_type not in ["linearGradient", "radialGradient"]:
        return False
    if complexity in [GradientComplexity.COMPLEX, GradientComplexity.UNSUPPORTED]:
        return False
    if advanced_features:
        return False
    return True


def calculate_gradient_metrics(
    element: ET.Element,
    stop_analysis: dict[str, Any],
    transform_analysis: dict[str, Any],
) -> GradientMetrics:
    """Calculate performance metrics for gradient."""
    _ = element
    base_memory = 1024
    stop_memory = stop_analysis["count"] * 64
    transform_memory = transform_analysis["transform_count"] * 128
    total_memory = base_memory + stop_memory + transform_memory

    base_time = 1.0
    stop_time = stop_analysis["count"] * 0.1
    transform_time = transform_analysis["complexity"] * 0.5
    total_time = base_time + stop_time + transform_time

    return GradientMetrics(
        stop_count=stop_analysis["count"],
        color_complexity=stop_analysis["color_complexity"],
        transform_complexity=transform_analysis["complexity"],
        memory_usage=total_memory,
        processing_time=total_time,
    )


def estimate_performance_impact(
    metrics: GradientMetrics,
    complexity: GradientComplexity,
) -> str:
    """Estimate performance impact."""
    if complexity == GradientComplexity.SIMPLE and metrics.stop_count <= 3:
        return "low"
    if complexity == GradientComplexity.MODERATE or metrics.stop_count <= 8:
        return "medium"
    if complexity == GradientComplexity.COMPLEX or metrics.stop_count <= 15:
        return "high"
    return "very_high"


def requires_preprocessing(
    element: ET.Element,
    transform_analysis: dict[str, Any],
    optimizations: list[GradientOptimization],
) -> bool:
    """Check if gradient would benefit from preprocessing."""
    _ = transform_analysis
    if element.get("data-gradient-optimized"):
        return False
    if GradientOptimization.TRANSFORM_FLATTENING in optimizations:
        return True
    if GradientOptimization.COLOR_SPACE_OPTIMIZATION in optimizations:
        return True
    if GradientOptimization.STOP_REDUCTION in optimizations:
        return True
    return False


__all__ = [
    "analyze_gradient_stops",
    "analyze_gradient_transforms",
    "assess_gradient_complexity",
    "assess_powerpoint_compatibility",
    "calculate_gradient_metrics",
    "check_advanced_features",
    "estimate_performance_impact",
    "identify_gradient_optimizations",
    "perform_gradient_analysis",
    "requires_preprocessing",
]
