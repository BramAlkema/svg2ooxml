"""Register the DrawingML path generator provider."""

from __future__ import annotations

from svg2ooxml.drawingml.generator import DrawingMLPathGenerator

from .registry import register_provider


def _factory() -> DrawingMLPathGenerator:
    return DrawingMLPathGenerator()


register_provider("drawingml_path_generator", _factory)


__all__ = ["_factory"]
