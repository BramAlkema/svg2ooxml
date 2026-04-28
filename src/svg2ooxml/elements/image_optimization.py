"""Image optimization marker helpers."""

from __future__ import annotations

from typing import Any

from lxml import etree as ET

from svg2ooxml.elements.image_types import (
    ImageAnalysis,
    ImageFormat,
    ImageOptimization,
)


class ImageOptimizationMixin:
    """Apply analysis-driven optimization markers to SVG image elements."""

    def apply_image_optimizations(
        self,
        element: ET.Element,
        analysis: ImageAnalysis,
        context: Any,  # noqa: ARG002 - reserved for future resource loading
    ) -> ET.Element:
        """Apply recommended optimizations to image element."""
        optimized_element = self._copy_element(element)

        for optimization in analysis.optimization_opportunities:
            try:
                if optimization == ImageOptimization.RESIZE:
                    optimized_element = self._apply_resize_optimization(
                        optimized_element, analysis
                    )
                elif optimization == ImageOptimization.EMBED_INLINE:
                    optimized_element = self._apply_embed_optimization(
                        optimized_element, analysis
                    )
                elif optimization == ImageOptimization.CONVERT_FORMAT:
                    optimized_element = self._apply_format_conversion(
                        optimized_element, analysis
                    )
                elif optimization == ImageOptimization.COMPRESS:
                    optimized_element = self._apply_compression(
                        optimized_element, analysis
                    )

                self.stats["optimizations_applied"] += 1

            except Exception as exc:
                self.logger.warning(
                    "Failed to apply optimization %s: %s",
                    optimization,
                    exc,
                )

        optimized_element.set("data-image-optimized", "true")

        return optimized_element

    def _copy_element(self, element: ET.Element) -> ET.Element:
        """Create a deep copy of an element."""
        copied = ET.Element(element.tag)

        for key, value in element.attrib.items():
            copied.set(key, value)

        if element.text:
            copied.text = element.text
        if element.tail:
            copied.tail = element.tail

        for child in element:
            copied.append(self._copy_element(child))

        return copied

    def _apply_resize_optimization(
        self, element: ET.Element, analysis: ImageAnalysis
    ) -> ET.Element:
        """Apply resize optimization."""
        max_width, max_height = 1920, 1080

        current_width = analysis.dimensions.width
        current_height = analysis.dimensions.height

        if current_width > max_width or current_height > max_height:
            scale_x = max_width / current_width
            scale_y = max_height / current_height
            scale = min(scale_x, scale_y)

            new_width = current_width * scale
            new_height = current_height * scale

            element.set("width", str(new_width))
            element.set("height", str(new_height))
            element.set("data-resize-applied", "true")

        return element

    def _apply_embed_optimization(
        self, element: ET.Element, analysis: ImageAnalysis  # noqa: ARG002
    ) -> ET.Element:
        """Apply embed optimization marker."""
        element.set("data-embed-pending", "true")
        return element

    def _apply_format_conversion(
        self, element: ET.Element, analysis: ImageAnalysis
    ) -> ET.Element:
        """Apply format conversion optimization marker."""
        if analysis.format == ImageFormat.SVG:
            element.set("data-convert-to-raster", "true")
            element.set("data-target-format", "png")

        return element

    def _apply_compression(
        self, element: ET.Element, analysis: ImageAnalysis  # noqa: ARG002
    ) -> ET.Element:
        """Apply compression optimization marker."""
        element.set("data-compress-image", "true")
        element.set("data-quality", "85")

        return element


__all__ = ["ImageOptimizationMixin"]
