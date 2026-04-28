"""Paint resolver bridge for resvg DrawingML text generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml import etree

from svg2ooxml.drawingml.paint_gradients import (
    _linear_gradient_to_fill_elem,
    _radial_gradient_to_fill_elem,
)
from svg2ooxml.ir.paint import LinearGradientPaint, RadialGradientPaint

if TYPE_CHECKING:
    from svg2ooxml.core.resvg.painting.paint import PaintReference


class DrawingMLTextPaintMixin:
    """Resolve text paint references into DrawingML fill elements."""

    def _resolve_gradient_fill(
        self,
        reference: PaintReference | None,
    ) -> etree._Element | None:
        """Resolve a PaintReference to a DrawingML gradient fill element."""
        if reference is None or self._paint_resolver is None:
            return None

        paint = self._paint_resolver(reference)
        if isinstance(paint, LinearGradientPaint):
            return _linear_gradient_to_fill_elem(paint)
        if isinstance(paint, RadialGradientPaint):
            return _radial_gradient_to_fill_elem(paint)
        return None


__all__ = ["DrawingMLTextPaintMixin"]
