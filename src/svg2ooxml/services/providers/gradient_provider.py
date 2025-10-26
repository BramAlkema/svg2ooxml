"""Register the gradient service provider."""

from __future__ import annotations

from svg2ooxml.services.gradient_service import GradientService

from .registry import register_provider


def _factory() -> GradientService:
    return GradientService()


register_provider("gradient", _factory)


__all__ = ["_factory"]
