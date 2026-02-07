"""
Image Processor

Enhanced image processing that integrates with the preprocessing pipeline
to provide optimized image conversion with PowerPoint optimization.

Features:
- Preprocessing-aware image analysis
- Transform flattening for images
- Image optimization and caching
- Format conversion and embedding
- Performance optimization for complex images
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from lxml import etree as ET

from svg2ooxml.services import ConversionServices

logger = logging.getLogger(__name__)


class ImageFormat(Enum):
    """Supported image formats."""
    PNG = "png"
    JPEG = "jpeg"
    SVG = "svg"
    GIF = "gif"
    BMP = "bmp"
    TIFF = "tiff"
    UNKNOWN = "unknown"


class ImageOptimization(Enum):
    """Image optimization strategies."""
    NONE = "none"
    COMPRESS = "compress"
    RESIZE = "resize"
    CONVERT_FORMAT = "convert_format"
    EMBED_INLINE = "embed_inline"


@dataclass
class ImageDimensions:
    """Image dimension information."""
    width: float
    height: float
    aspect_ratio: float
    units: str = "px"

    @property
    def is_square(self) -> bool:
        return abs(self.aspect_ratio - 1.0) < 0.01


@dataclass
class ImageAnalysis:
    """Result of image analysis."""
    element: ET.Element
    href: str
    format: ImageFormat
    dimensions: ImageDimensions
    file_size: int | None
    is_embedded: bool
    is_vector: bool
    requires_preprocessing: bool
    optimization_opportunities: list[ImageOptimization]
    powerpoint_compatible: bool
    estimated_performance_impact: str


class ImageProcessor:
    """
    Processes SVG image elements with preprocessing integration.

    Analyzes image characteristics, applies optimizations, and prepares
    images for PowerPoint embedding with optimal performance.
    """

    def __init__(self, services: ConversionServices):
        """
        Initialize image processor.

        Args:
            services: ConversionServices container
        """
        self.services = services
        self.logger = logging.getLogger(__name__)

        # Analysis cache
        self.analysis_cache: dict[str, ImageAnalysis] = {}

        # Statistics
        self.stats = {
            'images_processed': 0,
            'embedded_images': 0,
            'external_images': 0,
            'vector_images': 0,
            'raster_images': 0,
            'cache_hits': 0,
            'optimizations_applied': 0,
        }

    def analyze_image_element(self, element: ET.Element, context: Any) -> ImageAnalysis:
        """
        Analyze an image element and recommend optimizations.

        Args:
            element: Image element to analyze
            context: Conversion context

        Returns:
            Image analysis with optimization recommendations
        """
        # Generate cache key
        cache_key = self._generate_cache_key(element)

        # Check cache
        if cache_key in self.analysis_cache:
            self.stats['cache_hits'] += 1
            return self.analysis_cache[cache_key]

        self.stats['images_processed'] += 1

        # Perform analysis
        analysis = self._perform_image_analysis(element, context)

        # Cache result
        self.analysis_cache[cache_key] = analysis

        # Update statistics
        if analysis.is_embedded:
            self.stats['embedded_images'] += 1
        else:
            self.stats['external_images'] += 1

        if analysis.is_vector:
            self.stats['vector_images'] += 1
        else:
            self.stats['raster_images'] += 1

        return analysis

    def _perform_image_analysis(self, element: ET.Element, context: Any) -> ImageAnalysis:
        """Perform detailed image analysis."""
        # Extract image href
        href = self._extract_image_href(element)
        if not href:
            return self._create_invalid_image_analysis(element, "No href found")

        # Determine image format
        image_format = self._determine_image_format(href)

        # Extract dimensions
        dimensions = self._extract_image_dimensions(element, context)

        # Analyze image source
        is_embedded = self._is_embedded_image(href)
        file_size = self._estimate_file_size(href) if not is_embedded else None

        # Check if vector format
        is_vector = image_format in [ImageFormat.SVG]

        # Check preprocessing status
        requires_preprocessing = self._requires_preprocessing(element, image_format)

        # Identify optimization opportunities
        optimizations = self._identify_optimizations(element, href, image_format, dimensions)

        # Check PowerPoint compatibility
        powerpoint_compatible = self._assess_powerpoint_compatibility(image_format, dimensions)

        # Estimate performance impact
        performance_impact = self._estimate_performance_impact(dimensions, file_size, is_embedded)

        return ImageAnalysis(
            element=element,
            href=href,
            format=image_format,
            dimensions=dimensions,
            file_size=file_size,
            is_embedded=is_embedded,
            is_vector=is_vector,
            requires_preprocessing=requires_preprocessing,
            optimization_opportunities=optimizations,
            powerpoint_compatible=powerpoint_compatible,
            estimated_performance_impact=performance_impact,
        )

    def _extract_image_href(self, element: ET.Element) -> str | None:
        """Extract image href from various possible attributes."""
        # Check standard href attributes
        href_attrs = [
            '{http://www.w3.org/1999/xlink}href',
            'href',
            'xlink:href',
        ]

        for attr in href_attrs:
            href = element.get(attr)
            if href:
                return href.strip()

        return None

    def _determine_image_format(self, href: str) -> ImageFormat:
        """Determine image format from href."""
        if href.startswith('data:'):
            # Data URL - extract MIME type
            match = re.match(r'data:image/([^;]+)', href)
            if match:
                mime_type = match.group(1).lower()
                format_map = {
                    'png': ImageFormat.PNG,
                    'jpeg': ImageFormat.JPEG,
                    'jpg': ImageFormat.JPEG,
                    'svg+xml': ImageFormat.SVG,
                    'gif': ImageFormat.GIF,
                    'bmp': ImageFormat.BMP,
                    'tiff': ImageFormat.TIFF,
                }
                return format_map.get(mime_type, ImageFormat.UNKNOWN)
        else:
            # File URL - extract extension
            parsed = urlparse(href)
            path = parsed.path.lower()

            if path.endswith('.png'):
                return ImageFormat.PNG
            elif path.endswith(('.jpg', '.jpeg')):
                return ImageFormat.JPEG
            elif path.endswith('.svg'):
                return ImageFormat.SVG
            elif path.endswith('.gif'):
                return ImageFormat.GIF
            elif path.endswith('.bmp'):
                return ImageFormat.BMP
            elif path.endswith(('.tif', '.tiff')):
                return ImageFormat.TIFF

        return ImageFormat.UNKNOWN

    def _extract_image_dimensions(self, element: ET.Element, context: Any) -> ImageDimensions:
        """Extract image dimensions with unit conversion."""
        # Get width and height attributes
        width_str = element.get('width', '100')
        height_str = element.get('height', '100')

        # Parse dimensions with unit support
        width = self._parse_dimension(width_str, context)
        height = self._parse_dimension(height_str, context)

        # Calculate aspect ratio
        aspect_ratio = width / height if height != 0 else 1.0

        return ImageDimensions(
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            units="px",  # Normalized to pixels
        )

    def _parse_dimension(self, dimension_str: str, context: Any) -> float:
        """Parse dimension string with unit conversion."""
        if not dimension_str:
            return 100.0

        # Extract numeric value and unit
        match = re.match(r'([\d.]+)(\w*)', dimension_str.strip())
        if not match:
            return 100.0

        value = float(match.group(1))
        unit = match.group(2) or 'px'

        # Convert to pixels using services
        if hasattr(self.services, 'unit_converter'):
            try:
                # Use unit converter if available
                return self.services.unit_converter.to_pixels(value, unit)
            except Exception as e:
                self.logger.warning(f"Unit conversion failed: {e}")

        # Fallback conversion
        unit_map = {
            'px': 1.0,
            'pt': 1.333,  # 96/72
            'in': 96.0,
            'cm': 37.795,  # 96/2.54
            'mm': 3.7795,  # 96/25.4
            'em': 16.0,    # Approximate
            'rem': 16.0,   # Approximate
            '%': 1.0,       # Treat as pixels for now
        }

        return value * unit_map.get(unit.lower(), 1.0)

    def _is_embedded_image(self, href: str) -> bool:
        """Check if image is embedded as data URL."""
        return href.startswith('data:')

    def _estimate_file_size(self, href: str) -> int | None:
        """Estimate file size for external images."""
        if self._is_embedded_image(href):
            # For data URLs, estimate from base64 length
            if ',base64,' in href:
                base64_part = href.split(',base64,')[1]
                # Base64 encoding increases size by ~33%
                return int(len(base64_part) * 0.75)

        # Cannot estimate external file size without fetching
        return None

    def _requires_preprocessing(self, element: ET.Element, image_format: ImageFormat) -> bool:
        """Check if image requires preprocessing."""
        # Already has preprocessing metadata
        if element.get('data-image-optimized'):
            return False

        # Vector images might benefit from preprocessing
        if image_format == ImageFormat.SVG:
            return True

        # Images with transforms need preprocessing
        if element.get('transform'):
            return True

        # Images with complex attributes need preprocessing
        if element.get('clip-path') or element.get('mask'):
            return True

        return False

    def _identify_optimizations(self, element: ET.Element, href: str,
                              image_format: ImageFormat, dimensions: ImageDimensions) -> list[ImageOptimization]:
        """Identify optimization opportunities."""
        optimizations = []

        # Large images should be resized
        if dimensions.width > 2000 or dimensions.height > 2000:
            optimizations.append(ImageOptimization.RESIZE)

        # External images should be embedded for performance
        if not self._is_embedded_image(href):
            optimizations.append(ImageOptimization.EMBED_INLINE)

        # SVG images should be converted to raster for PowerPoint
        if image_format == ImageFormat.SVG:
            optimizations.append(ImageOptimization.CONVERT_FORMAT)

        # Large embedded images should be compressed
        if self._is_embedded_image(href):
            estimated_size = self._estimate_file_size(href)
            if estimated_size and estimated_size > 100000:  # 100KB
                optimizations.append(ImageOptimization.COMPRESS)

        return optimizations

    def _assess_powerpoint_compatibility(self, image_format: ImageFormat,
                                       dimensions: ImageDimensions) -> bool:
        """Assess PowerPoint compatibility."""
        # PowerPoint supports most common formats
        compatible_formats = [
            ImageFormat.PNG, ImageFormat.JPEG,
            ImageFormat.GIF, ImageFormat.BMP,
        ]

        if image_format not in compatible_formats:
            return False

        # Check dimension limits
        if dimensions.width > 5000 or dimensions.height > 5000:
            return False

        return True

    def _estimate_performance_impact(self, dimensions: ImageDimensions,
                                   file_size: int | None, is_embedded: bool) -> str:
        """Estimate performance impact."""
        pixel_count = dimensions.width * dimensions.height

        # Large images have high impact
        if pixel_count > 4000000:  # 2000x2000
            return 'high'

        # File size impact
        if file_size and file_size > 500000:  # 500KB
            return 'high'

        # Medium impact
        if pixel_count > 1000000 or (file_size and file_size > 100000):
            return 'medium'

        # External images have medium impact due to loading
        if not is_embedded:
            return 'medium'

        return 'low'

    def _create_invalid_image_analysis(self, element: ET.Element, reason: str) -> ImageAnalysis:
        """Create analysis for invalid image."""
        self.logger.warning(f"Invalid image element: {reason}")

        return ImageAnalysis(
            element=element,
            href="",
            format=ImageFormat.UNKNOWN,
            dimensions=ImageDimensions(width=0, height=0, aspect_ratio=1.0),
            file_size=None,
            is_embedded=False,
            is_vector=False,
            requires_preprocessing=False,
            optimization_opportunities=[],
            powerpoint_compatible=False,
            estimated_performance_impact='none',
        )

    def _generate_cache_key(self, element: ET.Element) -> str:
        """Generate cache key for element."""
        # Use href and key attributes as cache key
        href = self._extract_image_href(element) or ""
        width = element.get('width', '')
        height = element.get('height', '')
        transform = element.get('transform', '')

        key_data = f"{href}:{width}:{height}:{transform}"
        return hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()

    def apply_image_optimizations(self, element: ET.Element, analysis: ImageAnalysis,
                                context: Any) -> ET.Element:
        """Apply recommended optimizations to image element."""
        optimized_element = self._copy_element(element)

        for optimization in analysis.optimization_opportunities:
            try:
                if optimization == ImageOptimization.RESIZE:
                    optimized_element = self._apply_resize_optimization(optimized_element, analysis)
                elif optimization == ImageOptimization.EMBED_INLINE:
                    optimized_element = self._apply_embed_optimization(optimized_element, analysis)
                elif optimization == ImageOptimization.CONVERT_FORMAT:
                    optimized_element = self._apply_format_conversion(optimized_element, analysis)
                elif optimization == ImageOptimization.COMPRESS:
                    optimized_element = self._apply_compression(optimized_element, analysis)

                self.stats['optimizations_applied'] += 1

            except Exception as e:
                self.logger.warning(f"Failed to apply optimization {optimization}: {e}")

        # Mark as optimized
        optimized_element.set('data-image-optimized', 'true')

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

    def _apply_resize_optimization(self, element: ET.Element, analysis: ImageAnalysis) -> ET.Element:
        """Apply resize optimization."""
        # Calculate target dimensions (max 1920x1080 for PowerPoint)
        max_width, max_height = 1920, 1080

        current_width = analysis.dimensions.width
        current_height = analysis.dimensions.height

        if current_width > max_width or current_height > max_height:
            # Calculate scaling factor
            scale_x = max_width / current_width
            scale_y = max_height / current_height
            scale = min(scale_x, scale_y)

            # Apply new dimensions
            new_width = current_width * scale
            new_height = current_height * scale

            element.set('width', str(new_width))
            element.set('height', str(new_height))
            element.set('data-resize-applied', 'true')

        return element

    def _apply_embed_optimization(self, element: ET.Element, analysis: ImageAnalysis) -> ET.Element:
        """Apply embed optimization (placeholder - would require actual file loading)."""
        # In a real implementation, this would load the external image
        # and convert it to a data URL
        element.set('data-embed-pending', 'true')
        return element

    def _apply_format_conversion(self, element: ET.Element, analysis: ImageAnalysis) -> ET.Element:
        """Apply format conversion optimization."""
        if analysis.format == ImageFormat.SVG:
            # Mark for SVG to raster conversion
            element.set('data-convert-to-raster', 'true')
            element.set('data-target-format', 'png')

        return element

    def _apply_compression(self, element: ET.Element, analysis: ImageAnalysis) -> ET.Element:
        """Apply compression optimization."""
        # Mark for compression
        element.set('data-compress-image', 'true')
        element.set('data-quality', '85')  # JPEG quality 85%

        return element

    def get_processing_statistics(self) -> dict[str, int]:
        """Get processing statistics."""
        return self.stats.copy()

    def clear_cache(self) -> None:
        """Clear analysis cache."""
        self.analysis_cache.clear()

    def reset_statistics(self) -> None:
        """Reset processing statistics."""
        self.stats = {
            'images_processed': 0,
            'embedded_images': 0,
            'external_images': 0,
            'vector_images': 0,
            'raster_images': 0,
            'cache_hits': 0,
            'optimizations_applied': 0,
        }


def create_image_processor(services: ConversionServices) -> ImageProcessor:
    """
    Create an image processor with services.

    Args:
        services: ConversionServices container

    Returns:
        Configured ImageProcessor
    """
    return ImageProcessor(services)