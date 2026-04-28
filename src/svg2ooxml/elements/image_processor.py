"""Image processing facade with preprocessing-aware analysis and optimization."""

from __future__ import annotations

import logging
from typing import Any

from lxml import etree as ET

from svg2ooxml.elements.image_analysis import ImageAnalysisMixin
from svg2ooxml.elements.image_optimization import ImageOptimizationMixin
from svg2ooxml.elements.image_stats import ImageStatsMixin
from svg2ooxml.elements.image_types import (
    ImageAnalysis as ImageAnalysis,
)
from svg2ooxml.elements.image_types import (
    ImageDimensions as ImageDimensions,
)
from svg2ooxml.elements.image_types import (
    ImageFormat as ImageFormat,
)
from svg2ooxml.elements.image_types import (
    ImageOptimization as ImageOptimization,
)
from svg2ooxml.services import ConversionServices

logger = logging.getLogger(__name__)


class ImageProcessor(ImageAnalysisMixin, ImageOptimizationMixin, ImageStatsMixin):
    """Process SVG image elements with preprocessing integration."""

    def __init__(self, services: ConversionServices):
        """Initialize image processor."""
        self.services = services
        self.logger = logging.getLogger(__name__)
        self.analysis_cache: dict[str, ImageAnalysis] = {}
        self.stats = self._initial_stats()

    def analyze_image_element(self, element: ET.Element, context: Any) -> ImageAnalysis:
        """Analyze an image element and recommend optimizations."""
        cache_key = self._generate_cache_key(element)

        if cache_key in self.analysis_cache:
            self.stats["cache_hits"] += 1
            return self.analysis_cache[cache_key]

        self.stats["images_processed"] += 1
        analysis = self._perform_image_analysis(element, context)
        self.analysis_cache[cache_key] = analysis
        self._update_analysis_statistics(analysis)
        return analysis

    def _update_analysis_statistics(self, analysis: ImageAnalysis) -> None:
        if analysis.is_embedded:
            self.stats["embedded_images"] += 1
        else:
            self.stats["external_images"] += 1

        if analysis.is_vector:
            self.stats["vector_images"] += 1
        else:
            self.stats["raster_images"] += 1


def create_image_processor(services: ConversionServices) -> ImageProcessor:
    """Create an image processor with services."""
    return ImageProcessor(services)


__all__ = [
    "ImageAnalysis",
    "ImageDimensions",
    "ImageFormat",
    "ImageOptimization",
    "ImageProcessor",
    "create_image_processor",
]
