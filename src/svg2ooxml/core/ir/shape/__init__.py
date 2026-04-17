"""Shape conversion sub-modules."""

from svg2ooxml.core.ir.shape.fallback_converter import ShapeFallbackPathMixin
from svg2ooxml.core.ir.shape.image_converter import ShapeImageMixin
from svg2ooxml.core.ir.shape.resvg_converter import ShapeResvgPathMixin

__all__ = [
    "ShapeFallbackPathMixin",
    "ShapeImageMixin",
    "ShapeResvgPathMixin",
]
