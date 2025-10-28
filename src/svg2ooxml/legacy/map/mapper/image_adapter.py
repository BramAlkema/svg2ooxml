"""Image processing adapter for svg2ooxml mappers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from svg2ooxml.ir.scene import Image
from svg2ooxml.services.image_service import ImageResource, ImageService


@dataclass
class ImageProcessingResult:
    """Result of image preprocessing."""

    image_data: bytes | None
    format: str
    width: float
    height: float
    relationship_id: str
    metadata: dict[str, Any]


class ImageProcessingAdapter:
    """Lightweight image adapter that leverages svg2ooxml's ImageService."""

    def __init__(self, services=None) -> None:
        self._logger = logging.getLogger(__name__)
        self._services = services
        self._image_service: ImageService | None = None
        if services is not None:
            self._image_service = getattr(services, "image_service", None)
            if self._image_service is None and hasattr(services, "resolve"):
                self._image_service = services.resolve("image")
        if self._image_service is None:
            self._image_service = ImageService()

    def can_process_image(self, image: Image) -> bool:
        return bool(image.href or image.data)

    def process_image(self, image: Image, base_path: str | None = None) -> ImageProcessingResult:
        if not self.can_process_image(image):
            raise ValueError("Image does not contain data or href")

        resource: ImageResource | None = None
        if image.href:
            resource = self._resolve_href(image.href, base_path)

        data = image.data or (resource.data if resource else None)
        if data is None:
            raise ValueError("Unable to resolve image data")

        fmt = self._infer_format(image, resource)
        rel_id = f"rId{abs(hash((image.href, data))) % 1000000}"

        bounds = image.size
        metadata = {
            "source": resource.source if resource else ("inline" if image.data else None),
            "format": fmt,
        }

        return ImageProcessingResult(
            image_data=data,
            format=fmt,
            width=bounds.width,
            height=bounds.height,
            relationship_id=rel_id,
            metadata=metadata,
        )

    def _resolve_href(self, href: str, base_path: str | None) -> ImageResource | None:
        if self._image_service is None:
            return None
        return self._image_service.resolve(href)

    @staticmethod
    def _infer_format(image: Image, resource: ImageResource | None) -> str:
        if image.format:
            return image.format
        if resource and resource.mime_type:
            mime = resource.mime_type.lower()
            if "png" in mime:
                return "png"
            if "jpeg" in mime or "jpg" in mime:
                return "jpg"
            if "gif" in mime:
                return "gif"
            if "svg" in mime:
                return "svg"
        return "png"


def create_image_adapter(services=None) -> ImageProcessingAdapter:
    return ImageProcessingAdapter(services)


__all__ = ["ImageProcessingAdapter", "ImageProcessingResult", "create_image_adapter"]
