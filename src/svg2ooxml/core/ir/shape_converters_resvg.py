"""Resvg-backed shape conversion mixin."""

from __future__ import annotations

from svg2ooxml.core.ir.shape_converters_resvg_conversion import ResvgConversionMixin
from svg2ooxml.core.ir.shape_converters_resvg_support import ResvgSupportMixin


class ShapeResvgMixin(ResvgSupportMixin, ResvgConversionMixin):
    """Compose resvg conversion helpers under the legacy mixin name."""


__all__ = ["ShapeResvgMixin"]
