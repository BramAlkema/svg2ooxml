"""Register the image service provider."""

from __future__ import annotations

from svg2ooxml.services.image_service import ImageService

from .registry import register_provider


def _factory() -> ImageService:
    return ImageService()


register_provider("image", _factory)


__all__ = ["_factory"]
