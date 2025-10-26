"""Register the mask service provider."""

from __future__ import annotations

from svg2ooxml.services.mask_service import StructuredMaskService

from .registry import register_provider


def _factory() -> StructuredMaskService:
    return StructuredMaskService()


register_provider("mask_service", _factory)


__all__ = ["_factory"]
