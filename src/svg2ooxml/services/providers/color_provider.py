"""Register the color space service provider."""

from __future__ import annotations

from svg2ooxml.services.color_service import ColorSpaceService

from .registry import register_provider


def _factory() -> ColorSpaceService:
    return ColorSpaceService()


register_provider("color_space", _factory)


__all__ = ["_factory"]
