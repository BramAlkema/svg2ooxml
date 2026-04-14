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

from __future__ import annotations

import hashlib
import logging
import math
import re
import struct
import zlib
from dataclasses import dataclass
from enum import Enum
from typing import Any

from lxml import etree as ET

from svg2ooxml.common.geometry import Matrix2D, parse_transform_list
from svg2ooxml.color import summarize_palette
from svg2ooxml.core.styling.style_helpers import clean_color, parse_percentage
from svg2ooxml.services import ConversionServices

logger = logging.getLogger(__name__)


def _local_name(tag: str | None) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


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
            "patterns_analyzed": 0,
            "simple_patterns": 0,
            "complex_patterns": 0,
            "preset_matches": 0,
            "emf_fallbacks": 0,
            "cache_hits": 0,
            "optimizations_identified": 0,
        }

        # PowerPoint preset mapping
        self.preset_patterns = {
            "dots": ["pct5", "pct10", "pct20", "pct25", "pct30", "pct40", "pct50"],
            "horizontal": ["ltHorz", "horz", "dkHorz"],
            "vertical": ["ltVert", "vert", "dkVert"],
            "diagonal_up": ["ltUpDiag", "upDiag", "dkUpDiag"],
            "diagonal_down": ["ltDnDiag", "dnDiag", "dkDnDiag"],
            "cross": ["ltCross", "cross", "dkCross"],
        }

    def analyze_pattern_element(
        self, element: ET.Element, context: Any
    ) -> PatternAnalysis:
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
            self.stats["cache_hits"] += 1
            return self.analysis_cache[cache_key]

        self.stats["patterns_analyzed"] += 1

        # Perform analysis
        analysis = self._perform_pattern_analysis(element, context)

        # Cache result
        self.analysis_cache[cache_key] = analysis

        # Update statistics
        if analysis.complexity == PatternComplexity.SIMPLE:
            self.stats["simple_patterns"] += 1
        elif analysis.complexity in [
            PatternComplexity.MODERATE,
            PatternComplexity.COMPLEX,
        ]:
            self.stats["complex_patterns"] += 1

        if analysis.preset_candidate:
            self.stats["preset_matches"] += 1

        if analysis.emf_fallback_recommended:
            self.stats["emf_fallbacks"] += 1

        self.stats["optimizations_identified"] += len(
            analysis.optimization_opportunities
        )

        return analysis

    def build_tile_payload(
        self,
        element: ET.Element,
        *,
        analysis: PatternAnalysis,
    ) -> tuple[bytes, int, int] | None:
        """Build a reusable tile image for simple translated dot patterns."""
        if analysis.pattern_type != PatternType.DOTS:
            return None
        if analysis.complexity != PatternComplexity.SIMPLE:
            return None
        if analysis.geometry.transform_matrix is None:
            return None
        if not self._is_translation_only(analysis.geometry.transform_matrix):
            return None

        tile_width = max(float(analysis.geometry.tile_width), 0.0)
        tile_height = max(float(analysis.geometry.tile_height), 0.0)
        width_px = max(int(math.ceil(tile_width)), 1)
        height_px = max(int(math.ceil(tile_height)), 1)

        ellipses = list(
            self._iter_tile_ellipses(
                element,
                tile_width=tile_width,
                tile_height=tile_height,
            )
        )
        if not ellipses:
            return None

        pixels = bytearray(width_px * height_px * 4)
        for center_x, center_y, radius_x, radius_y, color, opacity in ellipses:
            self._rasterize_ellipse(
                pixels,
                width_px=width_px,
                height_px=height_px,
                center_x=center_x,
                center_y=center_y,
                radius_x=radius_x,
                radius_y=radius_y,
                color=color,
                opacity=opacity,
            )

        return self._encode_rgba_png(pixels, width_px, height_px), width_px, height_px

    def _perform_pattern_analysis(
        self, element: ET.Element, context: Any
    ) -> PatternAnalysis:
        """Perform detailed pattern analysis."""
        # Extract pattern geometry
        geometry = self._extract_pattern_geometry(element)

        # Analyze pattern content
        pattern_type, child_count, color_summary = self._analyze_pattern_content(
            element
        )
        colors_used = color_summary.get("palette", [])

        # Assess complexity
        complexity = self._assess_pattern_complexity(
            pattern_type, child_count, geometry
        )

        # Check for transforms
        has_transforms = bool(element.get("patternTransform", "").strip())

        # Check PowerPoint compatibility
        powerpoint_compatible = self._assess_powerpoint_compatibility(
            pattern_type,
            complexity,
            has_transforms,
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
        performance_impact = self._estimate_performance_impact(
            complexity, child_count, geometry, color_summary
        )

        # Check if preprocessing would help
        requires_preprocessing = self._requires_preprocessing(
            element,
            pattern_type,
            optimizations,
        )

        # Determine EMF fallback recommendation
        emf_fallback_recommended = self._should_use_emf_fallback(
            pattern_type,
            complexity,
            has_transforms,
            preset_candidate,
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
        width_str = element.get("width", "10")
        height_str = element.get("height", "10")

        # Parse dimensions
        width = self._parse_dimension(width_str)
        height = self._parse_dimension(height_str)

        # Calculate aspect ratio
        aspect_ratio = width / height if height != 0 else 1.0

        # Extract units and transforms
        units = element.get("patternUnits", "objectBoundingBox")
        content_units = element.get("patternContentUnits", "userSpaceOnUse")
        transform_str = element.get("patternTransform", "")

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
            if dim_str.endswith("%"):
                return float(dim_str[:-1]) / 100.0

            # Handle units
            if any(
                dim_str.endswith(unit) for unit in ["px", "pt", "em", "cm", "mm", "in"]
            ):
                # Extract numeric part
                import re

                match = re.match(r"([\d.]+)", dim_str)
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
            matrix_match = re.search(
                r"matrix\s*\(\s*([\d.-]+(?:\s*,?\s*[\d.-]+)*)\s*\)", transform_str
            )
            if matrix_match:
                values_str = matrix_match.group(1)
                values = [float(x.strip()) for x in re.split(r"[,\s]+", values_str)]
                if len(values) == 6:
                    return values

            # Handle simple transforms
            if "translate(" in transform_str:
                translate_match = re.search(
                    r"translate\s*\(\s*([\d.-]+)(?:\s*,?\s*([\d.-]+))?\s*\)",
                    transform_str,
                )
                if translate_match:
                    tx = float(translate_match.group(1))
                    ty = (
                        float(translate_match.group(2))
                        if translate_match.group(2)
                        else 0
                    )
                    return [1, 0, 0, 1, tx, ty]  # Identity + translation

        except Exception as e:
            self.logger.warning(f"Failed to parse transform: {e}")

        return None

    def _analyze_pattern_content(
        self, element: ET.Element
    ) -> tuple[PatternType, int, dict[str, object]]:
        """Analyze pattern content to determine type and complexity."""
        children = self._flatten_pattern_children(element)
        colors_raw: list[str] = []

        if not children:
            return PatternType.UNSUPPORTED, 0, summarize_palette(())

        # Analyze each child element
        shapes = {
            "circle": 0,
            "ellipse": 0,
            "rect": 0,
            "line": 0,
            "path": 0,
            "other": 0,
        }
        visible_children: list[ET.Element] = []

        for child in children:
            if not self._has_visible_paint(child):
                continue
            visible_children.append(child)
            tag = _local_name(child.tag)

            # Count shape types
            if tag in shapes:
                shapes[tag] += 1
            else:
                shapes["other"] += 1

            # Extract colors
            style = self._style_map(child)
            for attr in ["fill", "stroke"]:
                color = child.get(attr) or style.get(attr)
                if color and color.lower() not in ["none", "transparent"]:
                    colors_raw.append(color)

        child_count = len(visible_children)
        if child_count == 0:
            return PatternType.UNSUPPORTED, 0, summarize_palette(())

        # Determine pattern type based on content
        pattern_type = self._classify_pattern_type(shapes, visible_children)

        return pattern_type, child_count, summarize_palette(colors_raw)

    def _classify_pattern_type(
        self, shapes: dict[str, int], children: list[ET.Element]
    ) -> PatternType:
        """Classify pattern type based on shape analysis."""
        total_shapes = sum(shapes.values())

        # No recognizable shapes
        if total_shapes == 0 or shapes["other"] > total_shapes * 0.5:
            return PatternType.UNSUPPORTED

        # Dots pattern
        if shapes["circle"] > 0 or shapes["ellipse"] > 0:
            if shapes["circle"] + shapes["ellipse"] > total_shapes * 0.7:
                return PatternType.DOTS

        # Lines pattern
        if shapes["line"] > 0:
            if shapes["line"] > total_shapes * 0.7:
                return PatternType.LINES

        # Rectangle-based patterns
        if shapes["rect"] > 0:
            # Analyze rectangle dimensions to determine pattern type
            rect_analysis = self._analyze_rectangles(children)
            if rect_analysis["horizontal_lines"]:
                return PatternType.LINES
            elif rect_analysis["vertical_lines"]:
                return PatternType.LINES
            elif rect_analysis["grid"]:
                return PatternType.GRID

        # Path-based patterns
        if shapes["path"] > 0:
            path_analysis = self._analyze_paths(children)
            if path_analysis["dots"]:
                return PatternType.DOTS
            elif path_analysis["diagonal"]:
                return PatternType.DIAGONAL
            elif path_analysis["grid"]:
                return PatternType.CROSS

        # Mixed patterns
        if shapes["line"] > 0 and shapes["rect"] > 0:
            return PatternType.GRID

        return PatternType.CUSTOM

    def _analyze_rectangles(self, children: list[ET.Element]) -> dict[str, bool]:
        """Analyze rectangles to determine line patterns."""
        horizontal_lines = 0
        vertical_lines = 0
        squares = 0

        for child in children:
            if _local_name(child.tag) == "rect":
                try:
                    width = float(child.get("width", "1"))
                    height = float(child.get("height", "1"))

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
            "horizontal_lines": horizontal_lines > total_rects * 0.7,
            "vertical_lines": vertical_lines > total_rects * 0.7,
            "grid": squares > 0 or (horizontal_lines > 0 and vertical_lines > 0),
        }

    def _analyze_paths(self, children: list[ET.Element]) -> dict[str, bool]:
        """Analyze paths to determine pattern type."""
        dot_paths = 0
        diagonal_paths = 0
        grid_paths = 0

        for child in children:
            if _local_name(child.tag) == "path":
                path_data = child.get("d", "")
                path_data_upper = path_data.upper()

                # Simple analysis - look for diagonal movement
                if self._is_dot_like_path(child):
                    dot_paths += 1

                if "L" in path_data_upper and ("M" in path_data_upper):
                    # Check for diagonal patterns (simplified)
                    if "," in path_data:  # Likely has coordinates
                        diagonal_paths += 1

                # Look for grid-like patterns
                if path_data_upper.count("L") > 2:  # Multiple line segments
                    grid_paths += 1

        total_paths = len([c for c in children if _local_name(c.tag) == "path"])

        return {
            "dots": dot_paths > total_paths * 0.7,
            "diagonal": diagonal_paths > total_paths * 0.7,
            "grid": grid_paths > total_paths * 0.5,
        }

    def _assess_pattern_complexity(
        self, pattern_type: PatternType, child_count: int, geometry: PatternGeometry
    ) -> PatternComplexity:
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

        # Adjust for non-trivial transforms
        if geometry.transform_matrix and not self._is_translation_only(
            geometry.transform_matrix
        ):
            if type_complexity == PatternComplexity.SIMPLE:
                type_complexity = PatternComplexity.MODERATE

        return type_complexity

    def _assess_powerpoint_compatibility(
        self,
        pattern_type: PatternType,
        complexity: PatternComplexity,
        has_transforms: bool,
    ) -> bool:
        """Assess PowerPoint compatibility."""
        # PowerPoint has limited pattern support
        if complexity in [PatternComplexity.COMPLEX, PatternComplexity.UNSUPPORTED]:
            return False

        # Transforms may cause compatibility issues
        if has_transforms:
            return pattern_type in [PatternType.DOTS, PatternType.LINES]

        # Simple patterns are usually compatible
        return pattern_type in [
            PatternType.DOTS,
            PatternType.LINES,
            PatternType.DIAGONAL,
            PatternType.GRID,
            PatternType.CROSS,
        ]

    def _find_preset_candidate(
        self, pattern_type: PatternType, element: ET.Element, geometry: PatternGeometry
    ) -> str | None:
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
            return "cross"  # Generic cross pattern

        return None

    def _estimate_dot_density(
        self, element: ET.Element, geometry: PatternGeometry
    ) -> float:
        """Estimate dot density for percentage pattern mapping."""
        children = self._flatten_pattern_children(element)
        dot_count = sum(
            1
            for child in children
            if self._has_visible_paint(child)
            and (
                _local_name(child.tag) in {"circle", "ellipse"}
                or self._is_dot_like_path(child)
            )
        )

        # Estimate coverage based on tile size and dot count
        geometry.tile_width * geometry.tile_height
        estimated_coverage = min(dot_count * 0.1, 0.9)  # Simplified estimation

        return estimated_coverage

    def _map_density_to_preset(self, density: float) -> str:
        """Map density to PowerPoint percentage preset."""
        if density <= 0.05:
            return "pct5"
        elif density <= 0.15:
            return "pct10"
        elif density <= 0.22:
            return "pct20"
        elif density <= 0.35:
            return "pct30"
        elif density <= 0.45:
            return "pct40"
        elif density <= 0.55:
            return "pct50"
        else:
            return "pct75"

    def _determine_line_orientation(self, element: ET.Element) -> str:
        """Determine line orientation from pattern content."""
        # Simplified orientation detection
        children = self._flatten_pattern_children(element)

        for child in children:
            if _local_name(child.tag) == "line":
                try:
                    x1 = float(child.get("x1", "0"))
                    y1 = float(child.get("y1", "0"))
                    x2 = float(child.get("x2", "1"))
                    y2 = float(child.get("y2", "0"))

                    dx = abs(x2 - x1)
                    dy = abs(y2 - y1)

                    if dx > dy * 3:
                        return "horizontal"
                    elif dy > dx * 3:
                        return "vertical"

                except (ValueError, TypeError):
                    continue

        return "horizontal"  # Default

    def _map_orientation_to_preset(self, orientation: str) -> str:
        """Map line orientation to PowerPoint preset."""
        if orientation == "horizontal":
            return "horz"
        elif orientation == "vertical":
            return "vert"
        else:
            return "horz"

    def _determine_diagonal_direction(self, element: ET.Element) -> str:
        """Determine diagonal direction from pattern content."""
        # Simplified diagonal detection
        return "down"  # Default to down diagonal

    def _map_diagonal_to_preset(self, direction: str) -> str:
        """Map diagonal direction to PowerPoint preset."""
        if direction == "up":
            return "upDiag"
        else:
            return "dnDiag"

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

    def _requires_preprocessing(
        self,
        element: ET.Element,
        pattern_type: PatternType,
        optimizations: list[PatternOptimization],
    ) -> bool:
        """Check if pattern would benefit from preprocessing."""
        # Already has preprocessing metadata
        if element.get("data-pattern-optimized"):
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

    def _should_use_emf_fallback(
        self,
        pattern_type: PatternType,
        complexity: PatternComplexity,
        has_transforms: bool,
        preset_candidate: str | None,
    ) -> bool:
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
        key_data = ET.tostring(element, encoding="unicode")
        return hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()

    def _flatten_pattern_children(self, element: ET.Element) -> list[ET.Element]:
        flattened: list[ET.Element] = []

        def _walk(node: ET.Element) -> None:
            for child in node:
                if not isinstance(child.tag, str):
                    continue
                if _local_name(child.tag) in {"g", "a", "switch"}:
                    _walk(child)
                    continue
                flattened.append(child)

        _walk(element)
        return flattened

    def _iter_tile_ellipses(
        self,
        element: ET.Element,
        *,
        tile_width: float,
        tile_height: float,
    ):
        def _walk(node: ET.Element, transform: Matrix2D):
            current = transform
            transform_attr = node.get("transform")
            if transform_attr:
                try:
                    current = current.multiply(parse_transform_list(transform_attr))
                except Exception:
                    current = transform

            for child in node:
                if not isinstance(child.tag, str):
                    continue
                tag = _local_name(child.tag)
                if tag in {"g", "a", "switch"}:
                    yield from _walk(child, current)
                    continue
                fill_spec = self._pattern_fill_spec(child)
                if fill_spec is None:
                    continue
                ellipse = self._tile_ellipse_geometry(child, current)
                if ellipse is None:
                    continue
                center_x, center_y, radius_x, radius_y = ellipse
                if (
                    center_x + radius_x < 0.0
                    or center_y + radius_y < 0.0
                    or center_x - radius_x > tile_width
                    or center_y - radius_y > tile_height
                ):
                    continue
                yield (
                    center_x,
                    center_y,
                    radius_x,
                    radius_y,
                    fill_spec[0],
                    fill_spec[1],
                )

        yield from _walk(element, Matrix2D.identity())

    def _pattern_fill_spec(
        self, element: ET.Element
    ) -> tuple[tuple[int, int, int], float] | None:
        style = self._style_map(element)
        fill = element.get("fill") or style.get("fill")
        if not self._is_visible_paint_token(fill):
            return None
        color = clean_color(fill)
        if color is None:
            return None
        opacity = self._pattern_opacity(
            style.get("fill-opacity") or element.get("fill-opacity"),
            default=1.0,
        )
        opacity *= self._pattern_opacity(style.get("opacity") or element.get("opacity"))
        return (
            (
                int(color[0:2], 16),
                int(color[2:4], 16),
                int(color[4:6], 16),
            ),
            max(0.0, min(1.0, opacity)),
        )

    def _tile_ellipse_geometry(
        self,
        element: ET.Element,
        transform: Matrix2D,
    ) -> tuple[float, float, float, float] | None:
        if abs(transform.b) > 1e-9 or abs(transform.c) > 1e-9:
            return None

        tag = _local_name(element.tag)
        geometry: tuple[float, float, float, float] | None = None
        if tag == "circle":
            cx = self._parse_float_attr(element, "cx")
            cy = self._parse_float_attr(element, "cy")
            radius = self._parse_float_attr(element, "r")
            if cx is not None and cy is not None and radius is not None:
                geometry = (cx, cy, radius, radius)
        elif tag == "ellipse":
            cx = self._parse_float_attr(element, "cx")
            cy = self._parse_float_attr(element, "cy")
            rx = self._parse_float_attr(element, "rx")
            ry = self._parse_float_attr(element, "ry")
            if cx is not None and cy is not None and rx is not None and ry is not None:
                geometry = (cx, cy, rx, ry)
        elif tag == "path":
            geometry = self._path_ellipse_geometry(element)

        if geometry is None:
            return None

        cx, cy, rx, ry = geometry
        center_x, center_y = transform.transform_xy(cx, cy)
        edge_x, _edge_y = transform.transform_xy(cx + rx, cy)
        _up_x, up_y = transform.transform_xy(cx, cy + ry)
        radius_x = abs(edge_x - center_x)
        radius_y = abs(up_y - center_y)
        if radius_x <= 0.0 or radius_y <= 0.0:
            return None
        return center_x, center_y, radius_x, radius_y

    def _path_ellipse_geometry(
        self, element: ET.Element
    ) -> tuple[float, float, float, float] | None:
        sodipodi_ns = "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"
        cx = self._parse_float_attr(element, f"{{{sodipodi_ns}}}cx")
        cy = self._parse_float_attr(element, f"{{{sodipodi_ns}}}cy")
        rx = self._parse_float_attr(element, f"{{{sodipodi_ns}}}rx")
        ry = self._parse_float_attr(element, f"{{{sodipodi_ns}}}ry")
        if cx is not None and cy is not None and rx is not None and ry is not None:
            return (cx, cy, rx, ry)

        if not self._is_dot_like_path(element):
            return None

        path_data = element.get("d") or ""
        match = re.search(
            r"M\s*([-+]?[\d.]+)\s*,?\s*([-+]?[\d.]+)\s+"
            r"A\s*([-+]?[\d.]+)\s*,?\s*([-+]?[\d.]+)",
            path_data,
            flags=re.IGNORECASE,
        )
        if match is None:
            return None

        start_x = float(match.group(1))
        start_y = float(match.group(2))
        radius_x = float(match.group(3))
        radius_y = float(match.group(4))
        return (start_x - radius_x, start_y, radius_x, radius_y)

    @staticmethod
    def _parse_float_attr(element: ET.Element, attribute: str) -> float | None:
        value = element.get(attribute)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _pattern_opacity(value: str | None, default: float = 1.0) -> float:
        if value is None:
            return default
        try:
            return max(0.0, min(1.0, parse_percentage(value)))
        except Exception:
            return default

    def _rasterize_ellipse(
        self,
        pixels: bytearray,
        *,
        width_px: int,
        height_px: int,
        center_x: float,
        center_y: float,
        radius_x: float,
        radius_y: float,
        color: tuple[int, int, int],
        opacity: float,
    ) -> None:
        if opacity <= 0.0:
            return
        min_x = max(int(math.floor(center_x - radius_x - 1.0)), 0)
        max_x = min(int(math.ceil(center_x + radius_x + 1.0)), width_px)
        min_y = max(int(math.floor(center_y - radius_y - 1.0)), 0)
        max_y = min(int(math.ceil(center_y + radius_y + 1.0)), height_px)
        if min_x >= max_x or min_y >= max_y:
            return

        sample_offsets = (0.25, 0.75)
        inv_rx = 1.0 / radius_x
        inv_ry = 1.0 / radius_y

        for py in range(min_y, max_y):
            for px in range(min_x, max_x):
                coverage = 0
                for sy in sample_offsets:
                    for sx in sample_offsets:
                        dx = ((px + sx) - center_x) * inv_rx
                        dy = ((py + sy) - center_y) * inv_ry
                        if dx * dx + dy * dy <= 1.0:
                            coverage += 1
                if coverage == 0:
                    continue
                alpha = opacity * (coverage / 4.0)
                self._composite_rgba_pixel(
                    pixels,
                    width_px=width_px,
                    x=px,
                    y=py,
                    color=color,
                    alpha=alpha,
                )

    @staticmethod
    def _composite_rgba_pixel(
        pixels: bytearray,
        *,
        width_px: int,
        x: int,
        y: int,
        color: tuple[int, int, int],
        alpha: float,
    ) -> None:
        alpha = max(0.0, min(1.0, alpha))
        if alpha <= 0.0:
            return

        index = (y * width_px + x) * 4
        dst_r = pixels[index] / 255.0
        dst_g = pixels[index + 1] / 255.0
        dst_b = pixels[index + 2] / 255.0
        dst_a = pixels[index + 3] / 255.0
        src_r = color[0] / 255.0
        src_g = color[1] / 255.0
        src_b = color[2] / 255.0
        out_a = alpha + dst_a * (1.0 - alpha)
        if out_a <= 0.0:
            return
        out_r = (src_r * alpha + dst_r * dst_a * (1.0 - alpha)) / out_a
        out_g = (src_g * alpha + dst_g * dst_a * (1.0 - alpha)) / out_a
        out_b = (src_b * alpha + dst_b * dst_a * (1.0 - alpha)) / out_a
        pixels[index] = int(round(out_r * 255.0))
        pixels[index + 1] = int(round(out_g * 255.0))
        pixels[index + 2] = int(round(out_b * 255.0))
        pixels[index + 3] = int(round(out_a * 255.0))

    @staticmethod
    def _encode_rgba_png(pixels: bytearray, width_px: int, height_px: int) -> bytes:
        def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
            crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
            return (
                struct.pack(">I", len(data))
                + chunk_type
                + data
                + struct.pack(">I", crc)
            )

        rows = bytearray()
        row_stride = width_px * 4
        for row_idx in range(height_px):
            rows.append(0)
            start = row_idx * row_stride
            rows.extend(pixels[start : start + row_stride])

        return (
            b"\x89PNG\r\n\x1a\n"
            + _png_chunk(
                b"IHDR",
                struct.pack(">IIBBBBB", width_px, height_px, 8, 6, 0, 0, 0),
            )
            + _png_chunk(b"IDAT", zlib.compress(bytes(rows)))
            + _png_chunk(b"IEND", b"")
        )

    def _style_map(self, element: ET.Element) -> dict[str, str]:
        style = element.get("style")
        if not style:
            return {}
        declarations: dict[str, str] = {}
        for part in style.split(";"):
            if ":" not in part:
                continue
            name, value = part.split(":", 1)
            declarations[name.strip()] = value.strip()
        return declarations

    def _has_visible_paint(self, element: ET.Element) -> bool:
        style = self._style_map(element)
        fill = child_fill = element.get("fill") or style.get("fill")
        stroke = child_stroke = element.get("stroke") or style.get("stroke")
        return self._is_visible_paint_token(fill) or self._is_visible_paint_token(
            stroke
        )

    @staticmethod
    def _is_visible_paint_token(value: str | None) -> bool:
        if value is None:
            return False
        token = value.strip().lower()
        return bool(token) and token not in {"none", "transparent"}

    def _is_dot_like_path(self, element: ET.Element) -> bool:
        if _local_name(element.tag) != "path":
            return False
        if not self._has_visible_fill(element):
            return False

        path_data = (element.get("d") or "").upper()
        if (
            "A" in path_data
            and "L" not in path_data
            and "C" not in path_data
            and "Q" not in path_data
        ):
            return True

        for name, value in element.attrib.items():
            if _local_name(name) == "type" and value == "arc":
                return True
        return False

    def _has_visible_fill(self, element: ET.Element) -> bool:
        style = self._style_map(element)
        fill = element.get("fill") or style.get("fill")
        return self._is_visible_paint_token(fill)

    @staticmethod
    def _is_translation_only(transform_matrix: list[float]) -> bool:
        if len(transform_matrix) != 6:
            return False
        a, b, c, d, _tx, _ty = transform_matrix
        return (
            abs(a - 1.0) < 1e-9
            and abs(d - 1.0) < 1e-9
            and abs(b) < 1e-9
            and abs(c) < 1e-9
        )

    def get_processing_statistics(self) -> dict[str, int]:
        """Get processing statistics."""
        return self.stats.copy()

    def clear_cache(self) -> None:
        """Clear analysis cache."""
        self.analysis_cache.clear()

    def reset_statistics(self) -> None:
        """Reset processing statistics."""
        self.stats = {
            "patterns_analyzed": 0,
            "simple_patterns": 0,
            "complex_patterns": 0,
            "preset_matches": 0,
            "emf_fallbacks": 0,
            "cache_hits": 0,
            "optimizations_identified": 0,
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
