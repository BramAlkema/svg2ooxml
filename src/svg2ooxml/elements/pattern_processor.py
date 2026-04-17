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
from svg2ooxml.core.styling.style_helpers import clean_color
from svg2ooxml.services import ConversionServices

from .patterns._helpers import (
    flatten_pattern_children,
    has_visible_paint,
    is_dot_like_path,
    is_visible_paint_token,
    local_name,
    parse_float_attr,
    pattern_opacity,
    style_map,
)
from .patterns.classifier import (
    analyze_pattern_content,
    assess_pattern_complexity,
    assess_powerpoint_compatibility,
)
from .patterns.geometry import (
    estimate_performance_impact,
    extract_pattern_geometry,
    identify_pattern_optimizations,
    is_translation_only,
    requires_preprocessing,
    should_use_emf_fallback,
)
from .patterns.preset_matcher import find_preset_candidate

logger = logging.getLogger(__name__)


# Keep the old module-level helper available for backward compatibility
def _local_name(tag: str | None) -> str:
    return local_name(tag)


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
        if not is_translation_only(analysis.geometry.transform_matrix):
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
        geo_dict = extract_pattern_geometry(element)
        geometry = PatternGeometry(**geo_dict)

        # Analyze pattern content
        pattern_type, child_count, color_summary = analyze_pattern_content(
            element, PatternType
        )
        colors_used = color_summary.get("palette", [])

        # Assess complexity
        complexity = assess_pattern_complexity(
            pattern_type,
            child_count,
            geometry,
            PatternComplexity,
            is_translation_only,
        )

        # Check for transforms
        has_transforms = bool(element.get("patternTransform", "").strip())

        # Check PowerPoint compatibility
        powerpoint_compatible = assess_powerpoint_compatibility(
            pattern_type,
            complexity,
            has_transforms,
            PatternComplexity,
            PatternType,
        )

        # Find preset candidate
        preset_candidate = find_preset_candidate(
            pattern_type, element, geometry, PatternType
        )

        # Identify optimization opportunities
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

        # Estimate performance impact
        performance_impact = estimate_performance_impact(
            complexity, child_count, geometry, color_summary, PatternComplexity
        )

        # Check if preprocessing would help
        requires_preproc = requires_preprocessing(
            element,
            pattern_type,
            optimizations,
            PatternOptimization,
        )

        # Determine EMF fallback recommendation
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

    def _generate_cache_key(self, element: ET.Element) -> str:
        """Generate cache key for element."""
        key_data = ET.tostring(element, encoding="unicode")
        return hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()

    # ------------------------------------------------------------------
    # Tile rasterization helpers (kept in coordinator — tightly coupled)
    # ------------------------------------------------------------------

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
                tag = local_name(child.tag)
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
        sm = style_map(element)
        fill = element.get("fill") or sm.get("fill")
        if not is_visible_paint_token(fill):
            return None
        color = clean_color(fill)
        if color is None:
            return None
        opacity = pattern_opacity(
            sm.get("fill-opacity") or element.get("fill-opacity"),
            default=1.0,
        )
        opacity *= pattern_opacity(sm.get("opacity") or element.get("opacity"))
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

        tag = local_name(element.tag)
        geometry: tuple[float, float, float, float] | None = None
        if tag == "circle":
            cx = parse_float_attr(element, "cx")
            cy = parse_float_attr(element, "cy")
            radius = parse_float_attr(element, "r")
            if cx is not None and cy is not None and radius is not None:
                geometry = (cx, cy, radius, radius)
        elif tag == "ellipse":
            cx = parse_float_attr(element, "cx")
            cy = parse_float_attr(element, "cy")
            rx = parse_float_attr(element, "rx")
            ry = parse_float_attr(element, "ry")
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
        cx = parse_float_attr(element, f"{{{sodipodi_ns}}}cx")
        cy = parse_float_attr(element, f"{{{sodipodi_ns}}}cy")
        rx = parse_float_attr(element, f"{{{sodipodi_ns}}}rx")
        ry = parse_float_attr(element, f"{{{sodipodi_ns}}}ry")
        if cx is not None and cy is not None and rx is not None and ry is not None:
            return (cx, cy, rx, ry)

        if not is_dot_like_path(element):
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
