"""Shape conversion helpers for the IR converter."""

from __future__ import annotations

from svg2ooxml.core.ir.shape.fallback_converter import ShapeFallbackPathMixin
from svg2ooxml.core.ir.shape.image_converter import ShapeImageMixin
from svg2ooxml.core.ir.shape.resvg_converter import ShapeResvgPathMixin
from svg2ooxml.core.ir.shape_converters_fallbacks import ShapeFallbackMixin
from svg2ooxml.core.ir.shape_converters_foreign import ShapeForeignObjectMixin
from svg2ooxml.core.ir.shape_converters_policy import ShapeConversionPolicyMixin
from svg2ooxml.core.ir.shape_converters_resvg import ShapeResvgMixin
from svg2ooxml.core.ir.shape_converters_resvg_routing import ShapeResvgRoutingMixin
from svg2ooxml.core.ir.shape_converters_utils import (
    _ellipse_segments,
    _points_to_segments,
)
from svg2ooxml.core.styling import style_runtime as styles_runtime  # noqa: F401


class ShapeConversionMixin(
    ShapeResvgRoutingMixin,
    ShapeForeignObjectMixin,
    ShapeConversionPolicyMixin,
    ShapeResvgMixin,
    ShapeFallbackMixin,
    ShapeResvgPathMixin,
    ShapeFallbackPathMixin,
    ShapeImageMixin,
):
    """Mixin that houses individual SVG element conversion helpers."""

    _logger = None  # populated by IRConverter


__all__ = ["ShapeConversionMixin", "_ellipse_segments", "_points_to_segments"]
