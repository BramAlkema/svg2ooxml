"""Linear gradient conversion from resvg paint servers to IR paint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from svg2ooxml.core.resvg.geometry.matrix_bridge import (
    apply_matrix_to_xy as _apply_matrix_to_point,
)
from svg2ooxml.drawingml.bridges.resvg_gradient_stops import (
    gradient_id_or_none,
    gradient_stops_to_ir,
)
from svg2ooxml.ir.paint import LinearGradientPaint

if TYPE_CHECKING:
    from svg2ooxml.core.resvg.painting.gradients import LinearGradient


def linear_gradient_to_paint(gradient: LinearGradient) -> LinearGradientPaint:
    """Convert a resvg linear gradient to IR paint with coordinates transformed."""

    start = _apply_matrix_to_point(gradient.x1, gradient.y1, gradient.transform)
    end = _apply_matrix_to_point(gradient.x2, gradient.y2, gradient.transform)
    return LinearGradientPaint(
        stops=gradient_stops_to_ir(gradient.stops),
        start=start,
        end=end,
        transform=None,
        gradient_id=gradient_id_or_none(gradient.href),
        gradient_units=gradient.units,
        spread_method=gradient.spread_method,
    )


__all__ = ["linear_gradient_to_paint"]
