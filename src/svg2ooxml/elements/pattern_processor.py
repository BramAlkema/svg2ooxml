from __future__ import annotations

"""
Pattern Processor

Enhanced pattern processing that integrates with the preprocessing pipeline
and builds upon the existing pattern service and detection systems.

Features:
- Preprocessing-aware pattern analysis
- Pattern detection and classification
- PowerPoint preset matching
- EMF fallback optimization
- Performance optimization and caching
"""

import hashlib
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from lxml import etree as ET

from svg2ooxml.services import ConversionServices
from svg2ooxml.color import summarize_palette

logger = logging.getLogger(__name__)


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


class PatternProcessor:
    """
    Analyzes and processes SVG patterns with preprocessing integration.

    Provides pattern detection, PowerPoint preset mapping, and optimized
    EMF fallback when native patterns are not suitable.
    """

    def __init__(self, services: ConversionServices):
        """
        Initialize pattern processor.

        Args:
            services: ConversionServices container
        """
        self.services = services
        self.logger = logging.getLogger(__name__)

        # Analysis cache
        self.analysis_cache: dict[str, PatternAnalysis] = {}

        # Statistics
        self.stats = {
            'patterns_analyzed': 0,
            'simple_patterns': 0,
            'complex_patterns': 0,
            'preset_matches': 0,
            'emf_fallbacks': 0,
            'cache_hits': 0,
            'optimizations_identified': 0,
        }

        # PowerPoint preset mapping
        self.preset_patterns = {
            'dots': ['pct5', 'pct10', 'pct20', 'pct25', 'pct30', 'pct40', 'pct50'],
            'horizontal': ['ltHorz', 'horz', 'dkHorz'],
            'vertical': ['ltVert', 'vert', 'dkVert'],
            'diagonal_up': ['ltUpDiag', 'upDiag', 'dkUpDiag'],
            'diagonal_down': ['ltDnDiag', 'dnDiag', 'dkDnDiag'],
            'cross': ['ltCross', 'cross', 'dkCross'],
        }

    def analyze_pattern_element(self, element: ET.Element, context: Any) -> PatternAnalysis:
        """
        Analyze a pattern element and identify optimization opportunities.

        Args:
            element: Pattern element to analyze
            context: Conversion context

        Returns:
            Pattern analysis with recommendations
        """
        # Generate cache key
        cache_key = self._generate_cache_key(element)

        # Check cache
        if cache_key in self.analysis_cache:
            self.stats['cache_hits'] += 1
            return self.analysis_cache[cache_key]

        self.stats['patterns_analyzed'] += 1

        # Perform analysis
        analysis = self._perform_pattern_analysis(element, context)

        # Cache result
        self.analysis_cache[cache_key] = analysis

        # Update statistics
        if analysis.complexity == PatternComplexity.SIMPLE:
            self.stats['simple_patterns'] += 1
        elif analysis.complexity in [PatternComplexity.MODERATE, PatternComplexity.COMPLEX]:
            self.stats['complex_patterns'] += 1

        if analysis.preset_candidate:
            self.stats['preset_matches'] += 1

        if analysis.emf_fallback_recommended:
            self.stats['emf_fallbacks'] += 1

        self.stats['optimizations_identified'] += len(analysis.optimization_opportunities)

        return analysis

    def _perform_pattern_analysis(self, element: ET.Element, context: Any) -> PatternAnalysis:
        """Perform detailed pattern analysis."""
        # Extract pattern geometry
        geometry = self._extract_pattern_geometry(element)

        # Analyze pattern content
        pattern_type, child_count, color_summary = self._analyze_pattern_content(element)
        colors_used = color_summary.get("palette", [])

        # Assess complexity
        complexity = self._assess_pattern_complexity(pattern_type, child_count, geometry)

        # Check for transforms
        has_transforms = bool(element.get('patternTransform', '').strip())

        # Check PowerPoint compatibility
        powerpoint_compatible = self._assess_powerpoint_compatibility(
            pattern_type, complexity, has_transforms,
        )

        # Find preset candidate
        preset_candidate = self._find_preset_candidate(pattern_type, element, geometry)

        # Identify optimization opportunities
        optimizations = self._identify_pattern_optimizations(
            element,
            pattern_type,
            complexity,
            has_transforms,
            geometry,
            color_summary,
        )

        # Estimate performance impact
        performance_impact = self._estimate_performance_impact(complexity, child_count, geometry, color_summary)

        # Check if preprocessing would help
        requires_preprocessing = self._requires_preprocessing(
            element, pattern_type, optimizations,
        )

        # Determine EMF fallback recommendation
        emf_fallback_recommended = self._should_use_emf_fallback(
            pattern_type, complexity, has_transforms, preset_candidate,
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
            requires_preprocessing=requires_preprocessing,
            emf_fallback_recommended=emf_fallback_recommended,
        )

    def _extract_pattern_geometry(self, element: ET.Element) -> PatternGeometry:
        """Extract pattern geometric properties."""
        # Extract dimensions
        width_str = element.get('width', '10')
        height_str = element.get('height', '10')

        # Parse dimensions
        width = self._parse_dimension(width_str)
        height = self._parse_dimension(height_str)

        # Calculate aspect ratio
        aspect_ratio = width / height if height != 0 else 1.0

        # Extract units and transforms
        units = element.get('patternUnits', 'objectBoundingBox')
        content_units = element.get('patternContentUnits', 'userSpaceOnUse')
        transform_str = element.get('patternTransform', '')

        # Parse transform matrix
        transform_matrix = None
        if transform_str:
            transform_matrix = self._parse_transform_matrix(transform_str)

        return PatternGeometry(
            tile_width=width,
            tile_height=height,
            aspect_ratio=aspect_ratio,
            units=units,
            transform_matrix=transform_matrix,
            content_units=content_units,
        )

    def _parse_dimension(self, dim_str: str) -> float:
        """Parse dimension string to float value."""
        try:
            # Handle percentage
            if dim_str.endswith('%'):
                return float(dim_str[:-1]) / 100.0

            # Handle units
            if any(dim_str.endswith(unit) for unit in ['px', 'pt', 'em', 'cm', 'mm', 'in']):
                # Extract numeric part
                import re
                match = re.match(r'([\d.]+)', dim_str)
                if match:
                    return float(match.group(1))

            # Direct numeric value
            return float(dim_str)

        except (ValueError, TypeError):
            return 10.0  # Default value

    def _parse_transform_matrix(self, transform_str: str) -> list[float] | None:
        """Parse transform string to matrix values."""
        try:
            import re

            # Look for matrix() function
            matrix_match = re.search(r'matrix\s*\(\s*([\d.-]+(?:\s*,?\s*[\d.-]+)*)\s*\)', transform_str)
            if matrix_match:
                values_str = matrix_match.group(1)
                values = [float(x.strip()) for x in re.split(r'[,\s]+', values_str)]
                if len(values) == 6:
                    return values

            # Handle simple transforms
            if 'translate(' in transform_str:
                translate_match = re.search(r'translate\s*\(\s*([\d.-]+)(?:\s*,?\s*([\d.-]+))?\s*\)', transform_str)
                if translate_match:
                    tx = float(translate_match.group(1))
                    ty = float(translate_match.group(2)) if translate_match.group(2) else 0
                    return [1, 0, 0, 1, tx, ty]  # Identity + translation

        except Exception as e:
            self.logger.warning(f"Failed to parse transform: {e}")

        return None

    def _analyze_pattern_content(self, element: ET.Element) -> tuple[PatternType, int, dict[str, object]]:
        """Analyze pattern content to determine type and complexity."""
        children = list(element)
        child_count = len(children)
        colors_raw: list[str] = []

        if child_count == 0:
            return PatternType.UNSUPPORTED, 0, summarize_palette(())

        # Analyze each child element
        shapes = {'circle': 0, 'ellipse': 0, 'rect': 0, 'line': 0, 'path': 0, 'other': 0}

        for child in children:
            tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag

            # Count shape types
            if tag in shapes:
                shapes[tag] += 1
            else:
                shapes['other'] += 1

            # Extract colors
            for attr in ['fill', 'stroke']:
                color = child.get(attr)
                if color and color.lower() not in ['none', 'transparent']:
                    colors_raw.append(color)

        # Determine pattern type based on content
        pattern_type = self._classify_pattern_type(shapes, children)

        return pattern_type, child_count, summarize_palette(colors_raw)

    def _classify_pattern_type(self, shapes: dict[str, int], children: list[ET.Element]) -> PatternType:
        """Classify pattern type based on shape analysis."""
        total_shapes = sum(shapes.values())

        # No recognizable shapes
        if total_shapes == 0 or shapes['other'] > total_shapes * 0.5:
            return PatternType.UNSUPPORTED

        # Dots pattern
        if shapes['circle'] > 0 or shapes['ellipse'] > 0:
            if shapes['circle'] + shapes['ellipse'] > total_shapes * 0.7:
                return PatternType.DOTS

        # Lines pattern
        if shapes['line'] > 0:
            if shapes['line'] > total_shapes * 0.7:
                return PatternType.LINES

        # Rectangle-based patterns
        if shapes['rect'] > 0:
            # Analyze rectangle dimensions to determine pattern type
            rect_analysis = self._analyze_rectangles(children)
            if rect_analysis['horizontal_lines']:
                return PatternType.LINES
            elif rect_analysis['vertical_lines']:
                return PatternType.LINES
            elif rect_analysis['grid']:
                return PatternType.GRID

        # Path-based patterns
        if shapes['path'] > 0:
            path_analysis = self._analyze_paths(children)
            if path_analysis['diagonal']:
                return PatternType.DIAGONAL
            elif path_analysis['grid']:
                return PatternType.CROSS

        # Mixed patterns
        if shapes['line'] > 0 and shapes['rect'] > 0:
            return PatternType.GRID

        return PatternType.CUSTOM

    def _analyze_rectangles(self, children: list[ET.Element]) -> dict[str, bool]:
        """Analyze rectangles to determine line patterns."""
        horizontal_lines = 0
        vertical_lines = 0
        squares = 0

        for child in children:
            if child.tag.endswith('rect'):
                try:
                    width = float(child.get('width', '1'))
                    height = float(child.get('height', '1'))

                    # Check if it's a line (very thin rectangle)
                    if width > height * 3:
                        horizontal_lines += 1
                    elif height > width * 3:
                        vertical_lines += 1
                    elif abs(width - height) < min(width, height) * 0.1:
                        squares += 1

                except (ValueError, TypeError):
                    continue

        total_rects = horizontal_lines + vertical_lines + squares

        return {
            'horizontal_lines': horizontal_lines > total_rects * 0.7,
            'vertical_lines': vertical_lines > total_rects * 0.7,
            'grid': squares > 0 or (horizontal_lines > 0 and vertical_lines > 0),
        }

    def _analyze_paths(self, children: list[ET.Element]) -> dict[str, bool]:
        """Analyze paths to determine pattern type."""
        diagonal_paths = 0
        grid_paths = 0

        for child in children:
            if child.tag.endswith('path'):
                path_data = child.get('d', '')

                # Simple analysis - look for diagonal movement
                if 'L' in path_data and ('M' in path_data):
                    # Check for diagonal patterns (simplified)
                    if ',' in path_data:  # Likely has coordinates
                        diagonal_paths += 1

                # Look for grid-like patterns
                if path_data.count('L') > 2:  # Multiple line segments
                    grid_paths += 1

        total_paths = len([c for c in children if c.tag.endswith('path')])

        return {
            'diagonal': diagonal_paths > total_paths * 0.7,
            'grid': grid_paths > total_paths * 0.5,
        }

    def _assess_pattern_complexity(self, pattern_type: PatternType, child_count: int,
                                 geometry: PatternGeometry) -> PatternComplexity:
        """Assess overall pattern complexity."""
        # Base complexity from type
        type_complexity = {
            PatternType.DOTS: PatternComplexity.SIMPLE,
            PatternType.LINES: PatternComplexity.SIMPLE,
            PatternType.DIAGONAL: PatternComplexity.MODERATE,
            PatternType.GRID: PatternComplexity.MODERATE,
            PatternType.CROSS: PatternComplexity.MODERATE,
            PatternType.CUSTOM: PatternComplexity.COMPLEX,
            PatternType.UNSUPPORTED: PatternComplexity.UNSUPPORTED,
        }.get(pattern_type, PatternComplexity.COMPLEX)

        # Adjust for child count
        if child_count > 10:
            if type_complexity == PatternComplexity.SIMPLE:
                type_complexity = PatternComplexity.MODERATE
            elif type_complexity == PatternComplexity.MODERATE:
                type_complexity = PatternComplexity.COMPLEX

        # Adjust for transforms
        if geometry.transform_matrix:
            if type_complexity == PatternComplexity.SIMPLE:
                type_complexity = PatternComplexity.MODERATE

        return type_complexity

    def _assess_powerpoint_compatibility(self, pattern_type: PatternType,
                                       complexity: PatternComplexity,
                                       has_transforms: bool) -> bool:
        """Assess PowerPoint compatibility."""
        # PowerPoint has limited pattern support
        if complexity in [PatternComplexity.COMPLEX, PatternComplexity.UNSUPPORTED]:
            return False

        # Transforms may cause compatibility issues
        if has_transforms:
            return pattern_type in [PatternType.DOTS, PatternType.LINES]

        # Simple patterns are usually compatible
        return pattern_type in [
            PatternType.DOTS, PatternType.LINES, PatternType.DIAGONAL,
            PatternType.GRID, PatternType.CROSS,
        ]

    def _find_preset_candidate(self, pattern_type: PatternType, element: ET.Element,
                             geometry: PatternGeometry) -> str | None:
        """Find PowerPoint preset candidate for pattern."""
        if pattern_type == PatternType.DOTS:
            # Estimate dot density for percentage patterns
            density = self._estimate_dot_density(element, geometry)
            return self._map_density_to_preset(density)

        elif pattern_type == PatternType.LINES:
            # Determine line orientation
            orientation = self._determine_line_orientation(element)
            return self._map_orientation_to_preset(orientation)

        elif pattern_type == PatternType.DIAGONAL:
            # Determine diagonal direction
            direction = self._determine_diagonal_direction(element)
            return self._map_diagonal_to_preset(direction)

        elif pattern_type in [PatternType.GRID, PatternType.CROSS]:
            return 'cross'  # Generic cross pattern

        return None

    def _estimate_dot_density(self, element: ET.Element, geometry: PatternGeometry) -> float:
        """Estimate dot density for percentage pattern mapping."""
        # Simplified density estimation
        children = list(element)
        dot_count = sum(1 for child in children
                       if child.tag.endswith(('circle', 'ellipse')))

        # Estimate coverage based on tile size and dot count
        geometry.tile_width * geometry.tile_height
        estimated_coverage = min(dot_count * 0.1, 0.9)  # Simplified estimation

        return estimated_coverage

    def _map_density_to_preset(self, density: float) -> str:
        """Map density to PowerPoint percentage preset."""
        if density <= 0.05:
            return 'pct5'
        elif density <= 0.15:
            return 'pct10'
        elif density <= 0.22:
            return 'pct20'
        elif density <= 0.35:
            return 'pct30'
        elif density <= 0.45:
            return 'pct40'
        elif density <= 0.55:
            return 'pct50'
        else:
            return 'pct75'

    def _determine_line_orientation(self, element: ET.Element) -> str:
        """Determine line orientation from pattern content."""
        # Simplified orientation detection
        children = list(element)

        for child in children:
            if child.tag.endswith('line'):
                try:
                    x1 = float(child.get('x1', '0'))
                    y1 = float(child.get('y1', '0'))
                    x2 = float(child.get('x2', '1'))
                    y2 = float(child.get('y2', '0'))

                    dx = abs(x2 - x1)
                    dy = abs(y2 - y1)

                    if dx > dy * 3:
                        return 'horizontal'
                    elif dy > dx * 3:
                        return 'vertical'

                except (ValueError, TypeError):
                    continue

        return 'horizontal'  # Default

    def _map_orientation_to_preset(self, orientation: str) -> str:
        """Map line orientation to PowerPoint preset."""
        if orientation == 'horizontal':
            return 'horz'
        elif orientation == 'vertical':
            return 'vert'
        else:
            return 'horz'

    def _determine_diagonal_direction(self, element: ET.Element) -> str:
        """Determine diagonal direction from pattern content."""
        # Simplified diagonal detection
        return 'down'  # Default to down diagonal

    def _map_diagonal_to_preset(self, direction: str) -> str:
        """Map diagonal direction to PowerPoint preset."""
        if direction == 'up':
            return 'upDiag'
        else:
            return 'dnDiag'

    def _identify_pattern_optimizations(
        self,
        element: ET.Element,
        pattern_type: PatternType,
        complexity: PatternComplexity,
        has_transforms: bool,
        geometry: PatternGeometry,
        color_summary: dict[str, object],
    ) -> list[PatternOptimization]:
        """Identify optimization opportunities."""
        optimizations = []

        # Preset mapping opportunity
        if pattern_type in [PatternType.DOTS, PatternType.LINES, PatternType.DIAGONAL]:
            optimizations.append(PatternOptimization.PRESET_MAPPING)

        hue_spread = color_summary.get("hue_spread")
        unique_count = color_summary.get("unique", 0)

        # Color simplification
        if isinstance(hue_spread, (int, float)):
            if hue_spread < 35 and unique_count > 2:
                optimizations.append(PatternOptimization.COLOR_SIMPLIFICATION)
        elif unique_count and unique_count > 2:
            optimizations.append(PatternOptimization.COLOR_SIMPLIFICATION)

        recommended_space = color_summary.get("recommended_space")
        complexity_score = float(color_summary.get("complexity", 0.0) or 0.0)
        if recommended_space and recommended_space != "srgb":
            optimizations.append(PatternOptimization.COLOR_SPACE_OPTIMIZATION)
        elif complexity_score > 0.6:
            optimizations.append(PatternOptimization.COLOR_SPACE_OPTIMIZATION)

        # Transform flattening
        if has_transforms:
            optimizations.append(PatternOptimization.TRANSFORM_FLATTENING)

        # EMF optimization for complex patterns
        if complexity in [PatternComplexity.MODERATE, PatternComplexity.COMPLEX]:
            optimizations.append(PatternOptimization.EMF_OPTIMIZATION)

        # Tile optimization
        if geometry.tile_width > 100 or geometry.tile_height > 100:
            optimizations.append(PatternOptimization.TILE_OPTIMIZATION)

        return optimizations

    def _estimate_performance_impact(
        self,
        complexity: PatternComplexity,
        child_count: int,
        geometry: PatternGeometry,
        color_summary: dict[str, object],
    ) -> str:
        """Estimate performance impact."""
        color_complexity = float(color_summary.get("complexity", 0.0) or 0.0)

        if complexity == PatternComplexity.SIMPLE and child_count <= 3 and color_complexity < 0.4:
            return 'low'
        elif (
            complexity == PatternComplexity.MODERATE
            or child_count <= 8
            or color_complexity < 0.75
        ):
            return 'medium'
        elif (
            complexity == PatternComplexity.COMPLEX
            or child_count > 15
            or color_complexity >= 0.75
        ):
            return 'high'
        else:
            return 'very_high'

    def _requires_preprocessing(self, element: ET.Element, pattern_type: PatternType,
                              optimizations: list[PatternOptimization]) -> bool:
        """Check if pattern would benefit from preprocessing."""
        # Already has preprocessing metadata
        if element.get('data-pattern-optimized'):
            return False

        # Transform flattening would help
        if PatternOptimization.TRANSFORM_FLATTENING in optimizations:
            return True

        # Color simplification would help
        if PatternOptimization.COLOR_SIMPLIFICATION in optimizations:
            return True

        # Tile optimization would help
        if PatternOptimization.TILE_OPTIMIZATION in optimizations:
            return True

        return False

    def _should_use_emf_fallback(self, pattern_type: PatternType, complexity: PatternComplexity,
                               has_transforms: bool, preset_candidate: str | None) -> bool:
        """Determine if EMF fallback is recommended."""
        # Complex patterns should use EMF
        if complexity in [PatternComplexity.COMPLEX, PatternComplexity.UNSUPPORTED]:
            return True

        # Custom patterns without preset candidates
        if pattern_type == PatternType.CUSTOM and not preset_candidate:
            return True

        # Patterns with complex transforms
        if has_transforms and complexity != PatternComplexity.SIMPLE:
            return True

        return False

    def _generate_cache_key(self, element: ET.Element) -> str:
        """Generate cache key for element."""
        # Use element attributes and children as key
        attrs = sorted(element.attrib.items())
        children_count = len(list(element))

        # Include child information in key
        children_info = []
        for child in element:
            child_attrs = sorted(child.attrib.items())
            children_info.append(f"{child.tag}:{child_attrs}")

        key_data = f"{element.tag}:{attrs}:{children_count}:{':'.join(children_info)}"
        return hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()

    def get_processing_statistics(self) -> dict[str, int]:
        """Get processing statistics."""
        return self.stats.copy()

    def clear_cache(self) -> None:
        """Clear analysis cache."""
        self.analysis_cache.clear()

    def reset_statistics(self) -> None:
        """Reset processing statistics."""
        self.stats = {
            'patterns_analyzed': 0,
            'simple_patterns': 0,
            'complex_patterns': 0,
            'preset_matches': 0,
            'emf_fallbacks': 0,
            'cache_hits': 0,
            'optimizations_identified': 0,
        }


def create_pattern_processor(services: ConversionServices) -> PatternProcessor:
    """
    Create a pattern processor with services.

    Args:
        services: ConversionServices container

    Returns:
        Configured PatternProcessor
    """
    return PatternProcessor(services)
