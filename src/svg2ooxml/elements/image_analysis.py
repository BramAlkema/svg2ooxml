"""Image analysis helpers for SVG image elements."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from lxml import etree as ET

from svg2ooxml.common.units import UnitConverter
from svg2ooxml.common.units.lengths import resolve_length_px
from svg2ooxml.elements.image_types import (
    ImageAnalysis,
    ImageDimensions,
    ImageFormat,
    ImageOptimization,
)

_DATA_IMAGE_RE = re.compile(r"data:image/([^;]+)")
_DATA_URL_BASE64_MARKER = ",base64,"


class ImageAnalysisMixin:
    """Analyze SVG image attributes and produce optimization recommendations."""

    def _perform_image_analysis(self, element: ET.Element, context: Any) -> ImageAnalysis:
        """Perform detailed image analysis."""
        href = self._extract_image_href(element)
        if not href:
            return self._create_invalid_image_analysis(element, "No href found")

        image_format = self._determine_image_format(href)
        dimensions = self._extract_image_dimensions(element, context)
        is_embedded = self._is_embedded_image(href)
        file_size = self._estimate_file_size(href) if not is_embedded else None
        is_vector = image_format in [ImageFormat.SVG]
        requires_preprocessing = self._requires_preprocessing(element, image_format)
        optimizations = self._identify_optimizations(
            element, href, image_format, dimensions
        )
        powerpoint_compatible = self._assess_powerpoint_compatibility(
            image_format, dimensions
        )
        performance_impact = self._estimate_performance_impact(
            dimensions, file_size, is_embedded
        )

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
        href_attrs = [
            "{http://www.w3.org/1999/xlink}href",
            "href",
            "xlink:href",
        ]

        for attr in href_attrs:
            href = element.get(attr)
            if href:
                return href.strip()

        return None

    def _determine_image_format(self, href: str) -> ImageFormat:
        """Determine image format from href."""
        if href.startswith("data:"):
            match = _DATA_IMAGE_RE.match(href)
            if match:
                return _format_from_mime_token(match.group(1))
            return ImageFormat.UNKNOWN

        parsed = urlparse(href)
        path = parsed.path.lower()
        if path.endswith(".png"):
            return ImageFormat.PNG
        if path.endswith((".jpg", ".jpeg")):
            return ImageFormat.JPEG
        if path.endswith(".svg"):
            return ImageFormat.SVG
        if path.endswith(".gif"):
            return ImageFormat.GIF
        if path.endswith(".bmp"):
            return ImageFormat.BMP
        if path.endswith((".tif", ".tiff")):
            return ImageFormat.TIFF
        return ImageFormat.UNKNOWN

    def _extract_image_dimensions(
        self, element: ET.Element, context: Any
    ) -> ImageDimensions:
        """Extract image dimensions with unit conversion."""
        width_str = element.get("width", "100")
        height_str = element.get("height", "100")

        width = self._parse_dimension(width_str, context, axis="x")
        height = self._parse_dimension(height_str, context, axis="y")
        aspect_ratio = width / height if height != 0 else 1.0

        return ImageDimensions(
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            units="px",
        )

    def _parse_dimension(self, dimension_str: str, context: Any, *, axis: str) -> float:
        """Parse dimension string with unit conversion."""
        if not dimension_str:
            return 100.0

        conversion_context = getattr(context, "conversion", None) or getattr(
            context, "conversion_context", None
        )
        return resolve_length_px(
            dimension_str,
            conversion_context,
            axis=axis,
            default=100.0,
            unit_converter=UnitConverter(),
        )

    def _is_embedded_image(self, href: str) -> bool:
        """Check if image is embedded as data URL."""
        return href.startswith("data:")

    def _estimate_file_size(self, href: str) -> int | None:
        """Estimate file size for external images."""
        if self._is_embedded_image(href) and _DATA_URL_BASE64_MARKER in href:
            base64_part = href.split(_DATA_URL_BASE64_MARKER)[1]
            return int(len(base64_part) * 0.75)
        return None

    def _requires_preprocessing(
        self, element: ET.Element, image_format: ImageFormat
    ) -> bool:
        """Check if image requires preprocessing."""
        if element.get("data-image-optimized"):
            return False
        if image_format == ImageFormat.SVG:
            return True
        if element.get("transform"):
            return True
        if element.get("clip-path") or element.get("mask"):
            return True
        return False

    def _identify_optimizations(
        self,
        element: ET.Element,  # noqa: ARG002 - reserved for richer policies
        href: str,
        image_format: ImageFormat,
        dimensions: ImageDimensions,
    ) -> list[ImageOptimization]:
        """Identify optimization opportunities."""
        optimizations = []

        if dimensions.width > 2000 or dimensions.height > 2000:
            optimizations.append(ImageOptimization.RESIZE)
        if not self._is_embedded_image(href):
            optimizations.append(ImageOptimization.EMBED_INLINE)
        if image_format == ImageFormat.SVG:
            optimizations.append(ImageOptimization.CONVERT_FORMAT)
        if self._is_embedded_image(href):
            estimated_size = self._estimate_file_size(href)
            if estimated_size and estimated_size > 100000:
                optimizations.append(ImageOptimization.COMPRESS)

        return optimizations

    def _assess_powerpoint_compatibility(
        self,
        image_format: ImageFormat,
        dimensions: ImageDimensions,
    ) -> bool:
        """Assess PowerPoint compatibility."""
        compatible_formats = [
            ImageFormat.PNG,
            ImageFormat.JPEG,
            ImageFormat.GIF,
            ImageFormat.BMP,
        ]

        if image_format not in compatible_formats:
            return False
        return not (dimensions.width > 5000 or dimensions.height > 5000)

    def _estimate_performance_impact(
        self,
        dimensions: ImageDimensions,
        file_size: int | None,
        is_embedded: bool,
    ) -> str:
        """Estimate performance impact."""
        pixel_count = dimensions.width * dimensions.height

        if pixel_count > 4000000:
            return "high"
        if file_size and file_size > 500000:
            return "high"
        if pixel_count > 1000000 or (file_size and file_size > 100000):
            return "medium"
        if not is_embedded:
            return "medium"
        return "low"

    def _create_invalid_image_analysis(
        self, element: ET.Element, reason: str
    ) -> ImageAnalysis:
        """Create analysis for invalid image."""
        self.logger.warning("Invalid image element: %s", reason)

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
            estimated_performance_impact="none",
        )


def _format_from_mime_token(mime_type: str) -> ImageFormat:
    format_map = {
        "png": ImageFormat.PNG,
        "jpeg": ImageFormat.JPEG,
        "jpg": ImageFormat.JPEG,
        "svg+xml": ImageFormat.SVG,
        "gif": ImageFormat.GIF,
        "bmp": ImageFormat.BMP,
        "tiff": ImageFormat.TIFF,
    }
    return format_map.get(mime_type.lower(), ImageFormat.UNKNOWN)


__all__ = ["ImageAnalysisMixin"]
