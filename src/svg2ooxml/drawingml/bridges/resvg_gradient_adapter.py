"""Compatibility facade for resvg gradient paint conversion."""

from __future__ import annotations

from svg2ooxml.core.resvg.geometry.matrix_bridge import (
    matrix_to_numpy as _matrix_to_numpy,  # noqa: F401
)
from svg2ooxml.drawingml.bridges.resvg_gradient_linear import (
    linear_gradient_to_paint,
)
from svg2ooxml.drawingml.bridges.resvg_gradient_radial import (
    radial_gradient_to_paint,
)
from svg2ooxml.drawingml.bridges.resvg_gradient_stops import (
    _clamp,  # noqa: F401
    _color_to_hex,  # noqa: F401
)
from svg2ooxml.drawingml.bridges.resvg_gradient_transform import (
    TransformClass,
    _calculate_raster_size,  # noqa: F401
    classify_linear,
    decide_radial_policy,
)

__all__ = [
    "TransformClass",
    "classify_linear",
    "decide_radial_policy",
    "linear_gradient_to_paint",
    "radial_gradient_to_paint",
]
