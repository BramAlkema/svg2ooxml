"""Support mixin composition for resvg-backed shape conversion."""

from __future__ import annotations

from svg2ooxml.core.ir.shape_converters_resvg_paint import ResvgPaintSupportMixin
from svg2ooxml.core.ir.shape_converters_resvg_primitives import (
    ResvgPrimitiveSupportMixin,
)
from svg2ooxml.core.ir.shape_converters_resvg_styles import ResvgStyleSupportMixin
from svg2ooxml.core.ir.shape_converters_resvg_utils import ResvgUtilityMixin


class ResvgSupportMixin(
    ResvgStyleSupportMixin,
    ResvgPrimitiveSupportMixin,
    ResvgUtilityMixin,
    ResvgPaintSupportMixin,
):
    """Compose resvg support helpers under the legacy mixin name."""


__all__ = ["ResvgSupportMixin"]
