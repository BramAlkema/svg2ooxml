"""Image processor cache and statistics helpers."""

from __future__ import annotations

import hashlib

from lxml import etree as ET


class ImageStatsMixin:
    """Manage image processor cache keys and counters."""

    @staticmethod
    def _initial_stats() -> dict[str, int]:
        return {
            "images_processed": 0,
            "embedded_images": 0,
            "external_images": 0,
            "vector_images": 0,
            "raster_images": 0,
            "cache_hits": 0,
            "optimizations_applied": 0,
        }

    def _generate_cache_key(self, element: ET.Element) -> str:
        """Generate cache key for element."""
        href = self._extract_image_href(element) or ""
        width = element.get("width", "")
        height = element.get("height", "")
        transform = element.get("transform", "")

        key_data = f"{href}:{width}:{height}:{transform}"
        return hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()

    def get_processing_statistics(self) -> dict[str, int]:
        """Get processing statistics."""
        return self.stats.copy()

    def clear_cache(self) -> None:
        """Clear analysis cache."""
        self.analysis_cache.clear()

    def reset_statistics(self) -> None:
        """Reset processing statistics."""
        self.stats = self._initial_stats()


__all__ = ["ImageStatsMixin"]
