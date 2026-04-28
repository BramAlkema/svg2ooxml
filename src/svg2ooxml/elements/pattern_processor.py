"""
Pattern Processor

Enhanced pattern processing that integrates with the preprocessing pipeline
and builds upon the existing pattern service and detection systems.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from lxml import etree as ET

from svg2ooxml.elements.patterns._helpers import local_name
from svg2ooxml.elements.patterns.analyzer import perform_pattern_analysis
from svg2ooxml.elements.patterns.tile_renderer import (
    build_tile_payload as _build_tile_payload,
)
from svg2ooxml.elements.patterns.tile_renderer import (
    composite_rgba_pixel as _composite_rgba_pixel,
)
from svg2ooxml.elements.patterns.tile_renderer import (
    encode_rgba_png as _encode_rgba_png,
)
from svg2ooxml.elements.patterns.tile_renderer import (
    iter_tile_ellipses as _iter_tile_ellipses,
)
from svg2ooxml.elements.patterns.tile_renderer import (
    path_ellipse_geometry as _path_ellipse_geometry,
)
from svg2ooxml.elements.patterns.tile_renderer import (
    pattern_fill_spec as _pattern_fill_spec,
)
from svg2ooxml.elements.patterns.tile_renderer import (
    rasterize_ellipse as _rasterize_ellipse,
)
from svg2ooxml.elements.patterns.tile_renderer import (
    tile_ellipse_geometry as _tile_ellipse_geometry,
)
from svg2ooxml.elements.patterns.types import (
    PatternAnalysis,
    PatternComplexity,
    PatternGeometry,
    PatternOptimization,
    PatternType,
)
from svg2ooxml.services import ConversionServices

logger = logging.getLogger(__name__)


# Keep the old module-level helper available for backward compatibility
def _local_name(tag: str | None) -> str:
    return local_name(tag)


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
        self.analysis_cache: dict[str, PatternAnalysis] = {}
        self.stats = self._initial_stats()

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
        cache_key = self._generate_cache_key(element)

        if cache_key in self.analysis_cache:
            self.stats["cache_hits"] += 1
            return self.analysis_cache[cache_key]

        self.stats["patterns_analyzed"] += 1
        analysis = self._perform_pattern_analysis(element, context)
        self.analysis_cache[cache_key] = analysis
        self._update_statistics(analysis)

        return analysis

    def build_tile_payload(
        self,
        element: ET.Element,
        *,
        analysis: PatternAnalysis,
    ) -> tuple[bytes, int, int] | None:
        """Build a reusable tile image for simple translated dot patterns."""
        return _build_tile_payload(element, analysis=analysis)

    @staticmethod
    def _perform_pattern_analysis(
        element: ET.Element, context: Any
    ) -> PatternAnalysis:
        """Perform detailed pattern analysis."""
        return perform_pattern_analysis(element, context)

    @staticmethod
    def _generate_cache_key(element: ET.Element) -> str:
        """Generate cache key for element."""
        key_data = ET.tostring(element, encoding="unicode")
        return hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()

    def _update_statistics(self, analysis: PatternAnalysis) -> None:
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

    # Backward-compatible private helper delegates.
    _iter_tile_ellipses = staticmethod(_iter_tile_ellipses)
    _pattern_fill_spec = staticmethod(_pattern_fill_spec)
    _tile_ellipse_geometry = staticmethod(_tile_ellipse_geometry)
    _path_ellipse_geometry = staticmethod(_path_ellipse_geometry)
    _rasterize_ellipse = staticmethod(_rasterize_ellipse)
    _composite_rgba_pixel = staticmethod(_composite_rgba_pixel)
    _encode_rgba_png = staticmethod(_encode_rgba_png)

    # ------------------------------------------------------------------
    # Statistics / cache management
    # ------------------------------------------------------------------

    def get_processing_statistics(self) -> dict[str, int]:
        """Get processing statistics."""
        return self.stats.copy()

    def clear_cache(self) -> None:
        """Clear analysis cache."""
        self.analysis_cache.clear()

    def reset_statistics(self) -> None:
        """Reset processing statistics."""
        self.stats = self._initial_stats()

    @staticmethod
    def _initial_stats() -> dict[str, int]:
        return {
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


__all__ = [
    "PatternAnalysis",
    "PatternComplexity",
    "PatternGeometry",
    "PatternOptimization",
    "PatternProcessor",
    "PatternType",
    "create_pattern_processor",
]
