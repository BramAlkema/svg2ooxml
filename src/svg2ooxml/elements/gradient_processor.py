"""
Gradient Processor

Enhanced gradient processing that integrates with the preprocessing pipeline
and builds upon the existing high-performance gradient system.

Features:
- Preprocessing-aware gradient analysis
- Color system integration
- Transform flattening for gradients
- Performance optimization and caching
- PowerPoint DrawingML generation
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from lxml import etree as ET

from svg2ooxml.color import parse_color, summarize_palette
from svg2ooxml.services import ConversionServices

logger = logging.getLogger(__name__)


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

        # Analysis cache
        self.analysis_cache: dict[str, GradientAnalysis] = {}

        # Statistics
        self.stats = {
            'gradients_analyzed': 0,
            'simple_gradients': 0,
            'complex_gradients': 0,
            'optimizations_identified': 0,
            'cache_hits': 0,
            'preprocessing_benefits': 0,
        }

        # Performance thresholds
        self.complexity_thresholds = {
            'simple_stop_count': 5,
            'moderate_stop_count': 10,
            'complex_stop_count': 20,
        }

    def analyze_gradient_element(self, element: ET.Element, context: Any) -> GradientAnalysis:
        """
        Analyze a gradient element and identify optimization opportunities.

        Args:
            element: Gradient element to analyze
            context: Conversion context

        Returns:
            Gradient analysis with recommendations
        """
        # Generate cache key
        cache_key = self._generate_cache_key(element)

        # Check cache
        if cache_key in self.analysis_cache:
            self.stats['cache_hits'] += 1
            return self.analysis_cache[cache_key]

        self.stats['gradients_analyzed'] += 1

        # Perform analysis
        analysis = self._perform_gradient_analysis(element, context)

        # Cache result
        self.analysis_cache[cache_key] = analysis

        # Update statistics
        if analysis.complexity == GradientComplexity.SIMPLE:
            self.stats['simple_gradients'] += 1
        elif analysis.complexity in [GradientComplexity.MODERATE, GradientComplexity.COMPLEX]:
            self.stats['complex_gradients'] += 1

        self.stats['optimizations_identified'] += len(analysis.optimization_opportunities)

        if analysis.requires_preprocessing:
            self.stats['preprocessing_benefits'] += 1

        return analysis

    def _perform_gradient_analysis(self, element: ET.Element, context: Any) -> GradientAnalysis:
        """Perform detailed gradient analysis."""
        # Determine gradient type
        tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag
        gradient_type = tag if tag in ['linearGradient', 'radialGradient'] else 'unknown'

        # Analyze gradient stops
        stop_analysis = self._analyze_gradient_stops(element)

        # Analyze transforms
        transform_analysis = self._analyze_gradient_transforms(element)

        # Check for advanced features
        advanced_features = self._check_advanced_features(element)

        # Assess complexity
        complexity = self._assess_gradient_complexity(
            stop_analysis['count'], transform_analysis['complexity'], advanced_features,
        )

        # Identify optimization opportunities
        optimizations = self._identify_gradient_optimizations(
            element, stop_analysis, transform_analysis, advanced_features,
        )

        # Check PowerPoint compatibility
        powerpoint_compatible = self._assess_powerpoint_compatibility(
            gradient_type, complexity, advanced_features,
        )

        # Calculate metrics
        metrics = self._calculate_gradient_metrics(element, stop_analysis, transform_analysis)

        # Estimate performance impact
        performance_impact = self._estimate_performance_impact(metrics, complexity)

        # Check if preprocessing would help
        requires_preprocessing = self._requires_preprocessing(
            element, transform_analysis, optimizations,
        )

        return GradientAnalysis(
            element=element,
            gradient_type=gradient_type,
            complexity=complexity,
            stop_count=stop_analysis['count'],
            has_transforms=transform_analysis['has_transforms'],
            uses_advanced_features=advanced_features,
            color_spaces_used=stop_analysis['color_spaces'],
            colors_used=stop_analysis['colors_used'],
            color_statistics=stop_analysis['color_statistics'],
            optimization_opportunities=optimizations,
            powerpoint_compatible=powerpoint_compatible,
            estimated_performance_impact=performance_impact,
            metrics=metrics,
            requires_preprocessing=requires_preprocessing,
        )

    def _analyze_gradient_stops(self, element: ET.Element) -> dict[str, Any]:
        """Analyze gradient stops for optimization opportunities."""
        # Find stop elements
        stop_elements = element.findall('.//stop')
        if not stop_elements:
            stop_elements = element.findall('.//{http://www.w3.org/2000/svg}stop')

        stop_count = len(stop_elements)
        colors_raw: list[str] = []
        color_spaces = set()
        positions = []

        for stop in stop_elements:
            # Analyze position
            offset_str = stop.get('offset', '0')
            try:
                if offset_str.endswith('%'):
                    position = float(offset_str[:-1]) / 100.0
                else:
                    position = float(offset_str)
                positions.append(position)
            except (ValueError, TypeError):
                positions.append(0.0)

            # Analyze color
            color_str = stop.get('stop-color', '#000000')
            colors_raw.append(color_str)

            lower = color_str.strip().lower()
            if lower.startswith('#'):
                color_spaces.add('hex')
            elif lower.startswith('rgb(') or lower.startswith('rgba('):
                color_spaces.add('rgb')
            elif lower.startswith('hsl(') or lower.startswith('hsla('):
                color_spaces.add('hsl')
            else:
                color_spaces.add('named')

        palette_summary = summarize_palette(colors_raw)
        unique_colors = palette_summary["unique"]
        color_complexity = palette_summary["complexity"]
        recommended_space = palette_summary.get("recommended_space", "srgb")

        if palette_summary.get("advanced_available"):
            color_spaces.update({"oklab", "oklch"})
        if recommended_space:
            color_spaces.add(recommended_space)

        # Check for irregular spacing
        if len(positions) > 1:
            positions.sort()
            spacings = [positions[i+1] - positions[i] for i in range(len(positions)-1)]
            avg_spacing = sum(spacings) / len(spacings)
            spacing_variance = sum((s - avg_spacing)**2 for s in spacings) / len(spacings)
            irregular_spacing = spacing_variance > 0.01
        else:
            irregular_spacing = False

        return {
            'count': stop_count,
            'colors_used': palette_summary["palette"],
            'color_spaces': list(color_spaces),
            'unique_colors': unique_colors,
            'color_complexity': color_complexity,
            'positions': positions,
            'irregular_spacing': irregular_spacing,
            'color_statistics': palette_summary,
            'recommended_space': recommended_space,
            'advanced_available': palette_summary.get("advanced_available", False),
        }

    def _analyze_gradient_transforms(self, element: ET.Element) -> dict[str, Any]:
        """Analyze gradient transforms for optimization opportunities."""
        transform_str = element.get('gradientTransform', '')
        has_transforms = bool(transform_str.strip())

        if not has_transforms:
            return {
                'has_transforms': False,
                'complexity': 0.0,
                'transform_count': 0,
                'types': [],
            }

        # Count transform functions
        import re
        transform_functions = re.findall(r'(matrix|translate|scale|rotate|skewX|skewY)\s*\([^)]+\)', transform_str)
        transform_count = len(transform_functions)

        # Categorize transform types
        transform_types = [match.split('(')[0] for match in transform_functions]

        # Calculate complexity score
        complexity_weights = {
            'translate': 0.2,
            'scale': 0.3,
            'rotate': 0.5,
            'matrix': 1.0,
            'skewX': 0.7,
            'skewY': 0.7,
        }

        complexity = sum(complexity_weights.get(t, 0.5) for t in transform_types)

        return {
            'has_transforms': True,
            'complexity': complexity,
            'transform_count': transform_count,
            'types': transform_types,
            'transform_string': transform_str,
        }

    def _check_advanced_features(self, element: ET.Element) -> bool:
        """Check for advanced gradient features that may impact compatibility."""
        # Check for advanced attributes
        advanced_attrs = [
            'gradientUnits', 'spreadMethod', 'href', 'xlink:href',
        ]

        for attr in advanced_attrs:
            if element.get(attr):
                return True

        # Check for nested elements
        if len(list(element)) > 0:
            for child in element:
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if tag not in ['stop']:
                    return True

        return False

    def _assess_gradient_complexity(self, stop_count: int, transform_complexity: float,
                                  advanced_features: bool) -> GradientComplexity:
        """Assess overall gradient complexity."""
        # Start with stop count assessment
        if stop_count <= self.complexity_thresholds['simple_stop_count']:
            base_complexity = GradientComplexity.SIMPLE
        elif stop_count <= self.complexity_thresholds['moderate_stop_count']:
            base_complexity = GradientComplexity.MODERATE
        elif stop_count <= self.complexity_thresholds['complex_stop_count']:
            base_complexity = GradientComplexity.COMPLEX
        else:
            base_complexity = GradientComplexity.UNSUPPORTED

        # Adjust for transform complexity
        if transform_complexity > 1.0:
            if base_complexity == GradientComplexity.SIMPLE:
                base_complexity = GradientComplexity.MODERATE
            elif base_complexity == GradientComplexity.MODERATE:
                base_complexity = GradientComplexity.COMPLEX

        # Adjust for advanced features
        if advanced_features:
            if base_complexity == GradientComplexity.SIMPLE:
                base_complexity = GradientComplexity.MODERATE
            elif base_complexity == GradientComplexity.MODERATE:
                base_complexity = GradientComplexity.COMPLEX

        return base_complexity

    def _identify_gradient_optimizations(self, element: ET.Element, stop_analysis: dict[str, Any],
                                       transform_analysis: dict[str, Any],
                                       advanced_features: bool) -> list[GradientOptimization]:
        """Identify optimization opportunities."""
        optimizations = []

        color_stats = stop_analysis.get('color_statistics', {}) or {}

        # Color simplification using OKLCh spread heuristics
        hue_spread = color_stats.get("hue_spread")
        if hue_spread is not None:
            if hue_spread < 30 and stop_analysis['count'] > 4:
                optimizations.append(GradientOptimization.COLOR_SIMPLIFICATION)
        elif stop_analysis['color_complexity'] > 0.8 and stop_analysis['count'] > 5:
            optimizations.append(GradientOptimization.COLOR_SIMPLIFICATION)

        # Stop reduction
        if stop_analysis['count'] > self.complexity_thresholds['simple_stop_count']:
            if stop_analysis['unique_colors'] < stop_analysis['count'] * 0.7:
                optimizations.append(GradientOptimization.STOP_REDUCTION)
            elif isinstance(hue_spread, (int, float)) and hue_spread < 15:
                optimizations.append(GradientOptimization.STOP_REDUCTION)

        # Transform flattening
        if transform_analysis['has_transforms'] and transform_analysis['complexity'] > 0.5:
            optimizations.append(GradientOptimization.TRANSFORM_FLATTENING)

        # Color space optimization
        recommended_space = stop_analysis.get("recommended_space")
        if recommended_space and recommended_space != "srgb":
            optimizations.append(GradientOptimization.COLOR_SPACE_OPTIMIZATION)
        elif len(stop_analysis['color_spaces']) > 1:
            optimizations.append(GradientOptimization.COLOR_SPACE_OPTIMIZATION)

        # Vectorization benefits
        if stop_analysis['count'] > 3 or transform_analysis['transform_count'] > 1:
            optimizations.append(GradientOptimization.VECTORIZATION)

        return optimizations

    def _assess_powerpoint_compatibility(self, gradient_type: str, complexity: GradientComplexity,
                                       advanced_features: bool) -> bool:
        """Assess PowerPoint compatibility."""
        # PowerPoint has limited gradient support
        if gradient_type not in ['linearGradient', 'radialGradient']:
            return False

        # Complex gradients may not render correctly
        if complexity in [GradientComplexity.COMPLEX, GradientComplexity.UNSUPPORTED]:
            return False

        # Advanced features may not be supported
        if advanced_features:
            return False

        return True

    def _calculate_gradient_metrics(self, element: ET.Element, stop_analysis: dict[str, Any],
                                  transform_analysis: dict[str, Any]) -> GradientMetrics:
        """Calculate performance metrics for gradient."""
        # Estimate memory usage
        base_memory = 1024  # Base gradient overhead
        stop_memory = stop_analysis['count'] * 64  # Per-stop memory
        transform_memory = transform_analysis['transform_count'] * 128  # Per-transform memory
        total_memory = base_memory + stop_memory + transform_memory

        # Estimate processing time (arbitrary units)
        base_time = 1.0
        stop_time = stop_analysis['count'] * 0.1
        transform_time = transform_analysis['complexity'] * 0.5
        total_time = base_time + stop_time + transform_time

        return GradientMetrics(
            stop_count=stop_analysis['count'],
            color_complexity=stop_analysis['color_complexity'],
            transform_complexity=transform_analysis['complexity'],
            memory_usage=total_memory,
            processing_time=total_time,
        )

    def _estimate_performance_impact(self, metrics: GradientMetrics,
                                   complexity: GradientComplexity) -> str:
        """Estimate performance impact."""
        if complexity == GradientComplexity.SIMPLE and metrics.stop_count <= 3:
            return 'low'
        elif complexity == GradientComplexity.MODERATE or metrics.stop_count <= 8:
            return 'medium'
        elif complexity == GradientComplexity.COMPLEX or metrics.stop_count <= 15:
            return 'high'
        else:
            return 'very_high'

    def _requires_preprocessing(self, element: ET.Element, transform_analysis: dict[str, Any],
                              optimizations: list[GradientOptimization]) -> bool:
        """Check if gradient would benefit from preprocessing."""
        # Already has preprocessing metadata
        if element.get('data-gradient-optimized'):
            return False

        # Transform flattening would help
        if GradientOptimization.TRANSFORM_FLATTENING in optimizations:
            return True

        # Color space normalization would help
        if GradientOptimization.COLOR_SPACE_OPTIMIZATION in optimizations:
            return True

        # Stop reduction would help
        if GradientOptimization.STOP_REDUCTION in optimizations:
            return True

        return False

    def _generate_cache_key(self, element: ET.Element) -> str:
        """Generate cache key for element."""
        # Use gradient attributes and children as key
        attrs = sorted(element.attrib.items())
        children_count = len(list(element))

        # Include stop information in key
        stop_elements = element.findall('.//stop')
        stop_info = []
        for stop in stop_elements:
            stop_attrs = sorted(stop.attrib.items())
            stop_info.append(str(stop_attrs))

        key_data = f"{element.tag}:{attrs}:{children_count}:{':'.join(stop_info)}"
        return hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()

    def apply_gradient_optimizations(self, element: ET.Element, analysis: GradientAnalysis,
                                   context: Any) -> ET.Element:
        """Apply recommended optimizations to gradient element."""
        optimized_element = self._copy_element(element)

        for optimization in analysis.optimization_opportunities:
            try:
                if optimization == GradientOptimization.COLOR_SIMPLIFICATION:
                    optimized_element = self._apply_color_simplification(optimized_element, analysis)
                elif optimization == GradientOptimization.STOP_REDUCTION:
                    optimized_element = self._apply_stop_reduction(optimized_element, analysis)
                elif optimization == GradientOptimization.TRANSFORM_FLATTENING:
                    optimized_element = self._apply_transform_flattening(optimized_element, analysis)
                elif optimization == GradientOptimization.COLOR_SPACE_OPTIMIZATION:
                    optimized_element = self._apply_color_space_optimization(optimized_element, analysis)

            except Exception as e:
                self.logger.warning(f"Failed to apply optimization {optimization}: {e}")

        # Mark as optimized
        optimized_element.set('data-gradient-optimized', 'true')

        return optimized_element

    def _copy_element(self, element: ET.Element) -> ET.Element:
        """Create a deep copy of an element."""
        # Create new element with same tag
        copied = ET.Element(element.tag)

        # Copy attributes
        for key, value in element.attrib.items():
            copied.set(key, value)

        # Copy text content
        if element.text:
            copied.text = element.text
        if element.tail:
            copied.tail = element.tail

        # Copy children recursively
        for child in element:
            copied.append(self._copy_element(child))

        return copied

    def _apply_color_simplification(self, element: ET.Element, analysis: GradientAnalysis) -> ET.Element:
        """Apply color simplification optimization."""
        # Mark for color simplification
        element.set('data-color-simplified', 'true')
        return element

    def _apply_stop_reduction(self, element: ET.Element, analysis: GradientAnalysis) -> ET.Element:
        """Apply stop reduction optimization."""
        # Mark for stop reduction
        element.set('data-stops-reduced', 'true')
        return element

    def _apply_transform_flattening(self, element: ET.Element, analysis: GradientAnalysis) -> ET.Element:
        """Apply transform flattening optimization."""
        # Mark for transform flattening
        element.set('data-transform-flattened', 'true')
        return element

    def _apply_color_space_optimization(self, element: ET.Element, analysis: GradientAnalysis) -> ET.Element:
        """Apply color space optimization."""
        # Normalize all colors to the requested colour space
        stop_elements = element.findall('.//stop')
        if not stop_elements:
            stop_elements = element.findall('.//{http://www.w3.org/2000/svg}stop')

        recommended_space = "srgb"
        stats = getattr(analysis, "color_statistics", {})
        if isinstance(stats, dict):
            recommended_space = stats.get("recommended_space", "srgb")

        linear_metadata: list[tuple[float, float, float]] = []

        for stop in stop_elements:
            color_str = stop.get('stop-color', '#000000')
            try:
                normalized_color, linear_rgb = self._normalize_color(color_str, target_space=recommended_space)
                if normalized_color:
                    stop.set('stop-color', normalized_color)
                if linear_rgb is not None:
                    stop.set(
                        'data-linear-rgb',
                        "{:.6f},{:.6f},{:.6f}".format(*linear_rgb),
                    )
                    linear_metadata.append(linear_rgb)
            except Exception as e:
                self.logger.warning(f"Color normalization failed for '{color_str}': {e}")

        element.set('data-color-space', recommended_space)
        element.set('data-colors-normalized', 'true')
        return element

    def _normalize_color(self, value: str, *, target_space: str = "srgb") -> tuple[str | None, tuple[float, float, float] | None]:
        token = (value or '').strip()
        if not token:
            return None, None
        colour = parse_color(token)
        if colour is None:
            return None, None

        hex_value = colour.to_hex().upper()

        linear_rgb = None
        if target_space == "linear_rgb":
            linear_rgb = tuple(_srgb_channel_to_linear(component) for component in (colour.r, colour.g, colour.b))
        return hex_value, linear_rgb

    def get_processing_statistics(self) -> dict[str, int]:
        """Get processing statistics."""
        return self.stats.copy()

    def clear_cache(self) -> None:
        """Clear analysis cache."""
        self.analysis_cache.clear()

    def reset_statistics(self) -> None:
        """Reset processing statistics."""
        self.stats = {
            'gradients_analyzed': 0,
            'simple_gradients': 0,
            'complex_gradients': 0,
            'optimizations_identified': 0,
            'cache_hits': 0,
            'preprocessing_benefits': 0,
        }


def create_gradient_processor(services: ConversionServices) -> GradientProcessor:
    """
    Create a gradient processor with services.

    Args:
        services: ConversionServices container

    Returns:
        Configured GradientProcessor
    """
    return GradientProcessor(services)


def _srgb_channel_to_linear(component: float) -> float:
    component = max(0.0, min(1.0, component))
    if component <= 0.04045:
        return component / 12.92
    return ((component + 0.055) / 1.055) ** 2.4
