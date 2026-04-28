"""
Gradient Processor

Enhanced gradient processing that integrates with the preprocessing pipeline
and builds upon the existing high-performance gradient system.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from lxml import etree as ET

from svg2ooxml.elements.gradients.analyzer import (
    analyze_gradient_stops,
    analyze_gradient_transforms,
    assess_gradient_complexity,
    assess_powerpoint_compatibility,
    calculate_gradient_metrics,
    check_advanced_features,
    estimate_performance_impact,
    identify_gradient_optimizations,
    perform_gradient_analysis,
    requires_preprocessing,
)
from svg2ooxml.elements.gradients.optimizations import (
    apply_color_simplification,
    apply_color_space_optimization,
    apply_gradient_optimizations,
    apply_stop_reduction,
    apply_transform_flattening,
    copy_element,
    normalize_color,
)
from svg2ooxml.elements.gradients.optimizations import (
    srgb_channel_to_linear as _srgb_channel_to_linear,
)
from svg2ooxml.elements.gradients.types import (
    GradientAnalysis,
    GradientComplexity,
    GradientMetrics,
    GradientOptimization,
)
from svg2ooxml.services import ConversionServices

logger = logging.getLogger(__name__)


class GradientProcessor:
    """
    Analyzes and processes SVG gradients with preprocessing integration.

    Builds upon the existing high-performance gradient engine while adding
    preprocessing-aware capabilities and color system integration.
    """

    def __init__(self, services: ConversionServices):
        """
        Initialize gradient processor.

        Args:
            services: ConversionServices container
        """
        self.services = services
        self.logger = logging.getLogger(__name__)
        self.analysis_cache: dict[str, GradientAnalysis] = {}
        self.stats = self._initial_stats()
        self.complexity_thresholds = {
            "simple_stop_count": 5,
            "moderate_stop_count": 10,
            "complex_stop_count": 20,
        }

    def analyze_gradient_element(
        self,
        element: ET.Element,
        context: Any,
    ) -> GradientAnalysis:
        """
        Analyze a gradient element and identify optimization opportunities.

        Args:
            element: Gradient element to analyze
            context: Conversion context

        Returns:
            Gradient analysis with recommendations
        """
        cache_key = self._generate_cache_key(element)

        if cache_key in self.analysis_cache:
            self.stats["cache_hits"] += 1
            return self.analysis_cache[cache_key]

        self.stats["gradients_analyzed"] += 1
        analysis = self._perform_gradient_analysis(element, context)
        self.analysis_cache[cache_key] = analysis
        self._update_statistics(analysis)

        return analysis

    def _perform_gradient_analysis(
        self,
        element: ET.Element,
        context: Any,
    ) -> GradientAnalysis:
        """Perform detailed gradient analysis."""
        return perform_gradient_analysis(
            element,
            context,
            self.complexity_thresholds,
        )

    def _assess_gradient_complexity(
        self,
        stop_count: int,
        transform_complexity: float,
        advanced_features: bool,
    ) -> GradientComplexity:
        """Assess overall gradient complexity."""
        return assess_gradient_complexity(
            stop_count,
            transform_complexity,
            advanced_features,
            self.complexity_thresholds,
        )

    def _identify_gradient_optimizations(
        self,
        element: ET.Element,
        stop_analysis: dict[str, Any],
        transform_analysis: dict[str, Any],
        advanced_features: bool,
    ) -> list[GradientOptimization]:
        """Identify optimization opportunities."""
        return identify_gradient_optimizations(
            element,
            stop_analysis,
            transform_analysis,
            advanced_features,
            self.complexity_thresholds,
        )

    @staticmethod
    def _generate_cache_key(element: ET.Element) -> str:
        """Generate cache key for element."""
        attrs = sorted(element.attrib.items())
        children_count = len(list(element))

        stop_elements = element.findall(".//stop")
        stop_info = []
        for stop in stop_elements:
            stop_attrs = sorted(stop.attrib.items())
            stop_info.append(str(stop_attrs))

        key_data = f"{element.tag}:{attrs}:{children_count}:{':'.join(stop_info)}"
        return hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()

    def apply_gradient_optimizations(
        self,
        element: ET.Element,
        analysis: GradientAnalysis,
        context: Any,
    ) -> ET.Element:
        """Apply recommended optimizations to gradient element."""
        return apply_gradient_optimizations(
            element,
            analysis,
            context,
            logger=self.logger,
        )

    def _apply_color_space_optimization(
        self,
        element: ET.Element,
        analysis: GradientAnalysis,
    ) -> ET.Element:
        """Apply color space optimization."""
        return apply_color_space_optimization(element, analysis, logger=self.logger)

    def _update_statistics(self, analysis: GradientAnalysis) -> None:
        if analysis.complexity == GradientComplexity.SIMPLE:
            self.stats["simple_gradients"] += 1
        elif analysis.complexity in [
            GradientComplexity.MODERATE,
            GradientComplexity.COMPLEX,
        ]:
            self.stats["complex_gradients"] += 1

        self.stats["optimizations_identified"] += len(
            analysis.optimization_opportunities
        )

        if analysis.requires_preprocessing:
            self.stats["preprocessing_benefits"] += 1

    @staticmethod
    def _initial_stats() -> dict[str, int]:
        return {
            "gradients_analyzed": 0,
            "simple_gradients": 0,
            "complex_gradients": 0,
            "optimizations_identified": 0,
            "cache_hits": 0,
            "preprocessing_benefits": 0,
        }

    # Backward-compatible private helper delegates.
    _analyze_gradient_stops = staticmethod(analyze_gradient_stops)
    _analyze_gradient_transforms = staticmethod(analyze_gradient_transforms)
    _check_advanced_features = staticmethod(check_advanced_features)
    _assess_powerpoint_compatibility = staticmethod(assess_powerpoint_compatibility)
    _calculate_gradient_metrics = staticmethod(calculate_gradient_metrics)
    _estimate_performance_impact = staticmethod(estimate_performance_impact)
    _requires_preprocessing = staticmethod(requires_preprocessing)
    _copy_element = staticmethod(copy_element)
    _apply_color_simplification = staticmethod(apply_color_simplification)
    _apply_stop_reduction = staticmethod(apply_stop_reduction)
    _apply_transform_flattening = staticmethod(apply_transform_flattening)
    _normalize_color = staticmethod(normalize_color)

    def get_processing_statistics(self) -> dict[str, int]:
        """Get processing statistics."""
        return self.stats.copy()

    def clear_cache(self) -> None:
        """Clear analysis cache."""
        self.analysis_cache.clear()

    def reset_statistics(self) -> None:
        """Reset processing statistics."""
        self.stats = self._initial_stats()


def create_gradient_processor(services: ConversionServices) -> GradientProcessor:
    """
    Create a gradient processor with services.

    Args:
        services: ConversionServices container

    Returns:
        Configured GradientProcessor
    """
    return GradientProcessor(services)


__all__ = [
    "GradientAnalysis",
    "GradientComplexity",
    "GradientMetrics",
    "GradientOptimization",
    "GradientProcessor",
    "_srgb_channel_to_linear",
    "create_gradient_processor",
]
