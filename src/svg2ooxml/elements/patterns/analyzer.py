"""Pattern analysis orchestration."""

from __future__ import annotations

from typing import Any

from lxml import etree as ET

from svg2ooxml.elements.patterns.classifier import (
    analyze_pattern_content,
    assess_pattern_complexity,
    assess_powerpoint_compatibility,
)
from svg2ooxml.elements.patterns.geometry import (
    estimate_performance_impact,
    extract_pattern_geometry,
    identify_pattern_optimizations,
    is_translation_only,
    requires_preprocessing,
    should_use_emf_fallback,
)
from svg2ooxml.elements.patterns.preset_matcher import find_preset_candidate
from svg2ooxml.elements.patterns.types import (
    PatternAnalysis,
    PatternComplexity,
    PatternGeometry,
    PatternOptimization,
    PatternType,
)


def perform_pattern_analysis(element: ET.Element, context: Any) -> PatternAnalysis:
    """Perform detailed pattern analysis."""
    _ = context
    geometry = PatternGeometry(**extract_pattern_geometry(element))

    pattern_type, child_count, color_summary = analyze_pattern_content(
        element, PatternType
    )
    colors_used = color_summary.get("palette", [])

    complexity = assess_pattern_complexity(
        pattern_type,
        child_count,
        geometry,
        PatternComplexity,
        is_translation_only,
    )
    has_transforms = bool(element.get("patternTransform", "").strip())
    powerpoint_compatible = assess_powerpoint_compatibility(
        pattern_type,
        complexity,
        has_transforms,
        PatternComplexity,
        PatternType,
    )
    preset_candidate = find_preset_candidate(
        pattern_type, element, geometry, PatternType
    )
    optimizations = identify_pattern_optimizations(
        element,
        pattern_type,
        complexity,
        has_transforms,
        geometry,
        color_summary,
        PatternType,
        PatternComplexity,
        PatternOptimization,
    )
    performance_impact = estimate_performance_impact(
        complexity, child_count, geometry, color_summary, PatternComplexity
    )
    requires_preproc = requires_preprocessing(
        element,
        pattern_type,
        optimizations,
        PatternOptimization,
    )
    emf_fallback_recommended = should_use_emf_fallback(
        pattern_type,
        complexity,
        has_transforms,
        preset_candidate,
        PatternComplexity,
        PatternType,
    )

    return PatternAnalysis(
        element=element,
        pattern_type=pattern_type,
        complexity=complexity,
        geometry=geometry,
        has_transforms=has_transforms,
        child_count=child_count,
        colors_used=colors_used,
        color_statistics=color_summary,
        powerpoint_compatible=powerpoint_compatible,
        preset_candidate=preset_candidate,
        optimization_opportunities=optimizations,
        estimated_performance_impact=performance_impact,
        requires_preprocessing=requires_preproc,
        emf_fallback_recommended=emf_fallback_recommended,
    )


__all__ = ["perform_pattern_analysis"]
