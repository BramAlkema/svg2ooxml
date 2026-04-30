"""Transform helpers for rasterized SVG filter fallbacks."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

MatrixTuple = tuple[float, float, float, float, float, float]


def matrix_from_options(options: Mapping[str, Any] | None) -> MatrixTuple | None:
    if not isinstance(options, Mapping):
        return None
    raw = options.get("ctm") or options.get("filter_transform")
    if isinstance(raw, Mapping):
        try:
            return (
                float(raw.get("a", 1.0)),
                float(raw.get("b", 0.0)),
                float(raw.get("c", 0.0)),
                float(raw.get("d", 1.0)),
                float(raw.get("e", 0.0)),
                float(raw.get("f", 0.0)),
            )
        except (TypeError, ValueError):
            return None
    if isinstance(raw, (list, tuple)) and len(raw) >= 6:
        try:
            return tuple(float(value) for value in raw[:6])  # type: ignore[return-value]
        except (TypeError, ValueError):
            return None
    return None


def axis_scales(matrix: MatrixTuple | None) -> tuple[float, float]:
    if matrix is None:
        return (1.0, 1.0)
    a, b, c, d, _, _ = matrix
    scale_x = math.hypot(a, b)
    scale_y = math.hypot(c, d)
    return (
        scale_x if math.isfinite(scale_x) and scale_x > 0.0 else 1.0,
        scale_y if math.isfinite(scale_y) and scale_y > 0.0 else 1.0,
    )


def transform_user_space_bounds(
    bounds: tuple[float, float, float, float],
    matrix: MatrixTuple | None,
) -> tuple[float, float, float, float]:
    if matrix is None:
        return bounds
    min_x, min_y, max_x, max_y = bounds
    corners = (
        _transform_point(min_x, min_y, matrix),
        _transform_point(max_x, min_y, matrix),
        _transform_point(max_x, max_y, matrix),
        _transform_point(min_x, max_y, matrix),
    )
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    return (min(xs), min(ys), max(xs), max(ys))


def transform_bounds_mapping(
    bounds: Mapping[str, Any] | None,
    matrix: MatrixTuple | None,
) -> dict[str, float] | None:
    if not isinstance(bounds, Mapping):
        return None
    try:
        x = float(bounds.get("x", 0.0))
        y = float(bounds.get("y", 0.0))
        width = float(bounds.get("width", 0.0))
        height = float(bounds.get("height", 0.0))
    except (TypeError, ValueError):
        return None
    transformed = transform_user_space_bounds((x, y, x + width, y + height), matrix)
    x0, y0, x1, y1 = transformed
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def scale_plan_user_space_primitives(plan: Any, matrix: MatrixTuple | None) -> None:
    scale_x, scale_y = axis_scales(matrix)
    if abs(scale_x - 1.0) <= 1e-9 and abs(scale_y - 1.0) <= 1e-9:
        return
    for primitive_plan in getattr(plan, "primitives", ()) or ():
        tag = str(getattr(primitive_plan, "tag", "")).lower()
        extra = getattr(primitive_plan, "extra", None)
        if not isinstance(extra, dict):
            continue
        if tag == "feoffset":
            extra["dx"] = _scaled(extra.get("dx", 0.0), scale_x)
            extra["dy"] = _scaled(extra.get("dy", 0.0), scale_y)
        elif tag == "fegaussianblur":
            sigma = extra.get("std_deviation", (0.0, 0.0))
            if isinstance(sigma, (list, tuple)) and len(sigma) >= 2:
                extra["std_deviation"] = (
                    _scaled(sigma[0], scale_x),
                    _scaled(sigma[1], scale_y),
                )
        elif tag == "femorphology":
            extra["radius_x"] = _scaled(extra.get("radius_x", 0.0), scale_x)
            extra["radius_y"] = _scaled(extra.get("radius_y", 0.0), scale_y)
        elif tag == "fedisplacementmap":
            extra["scale"] = _scaled(extra.get("scale", 0.0), (scale_x + scale_y) / 2.0)


def _transform_point(x: float, y: float, matrix: MatrixTuple) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    return (a * x + c * y + e, b * x + d * y + f)


def _scaled(value: Any, scale: float) -> float:
    try:
        return float(value) * scale
    except (TypeError, ValueError):
        return 0.0


__all__ = [
    "axis_scales",
    "matrix_from_options",
    "scale_plan_user_space_primitives",
    "transform_bounds_mapping",
    "transform_user_space_bounds",
]
