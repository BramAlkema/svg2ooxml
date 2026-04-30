"""Radial gradient conversion from resvg paint servers to IR paint."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from svg2ooxml.core.resvg.geometry.matrix_bridge import (
    apply_matrix_to_xy as _apply_matrix_to_point,
)
from svg2ooxml.core.resvg.geometry.matrix_bridge import (
    matrix_to_numpy as _matrix_to_numpy,
)
from svg2ooxml.drawingml.bridges.resvg_gradient_stops import (
    gradient_id_or_none,
    gradient_stops_to_ir,
)
from svg2ooxml.drawingml.bridges.resvg_gradient_transform import (
    _calculate_raster_size,
    decide_radial_policy,
)
from svg2ooxml.ir.paint import RadialGradientPaint

if TYPE_CHECKING:
    from svg2ooxml.core.resvg.painting.gradients import RadialGradient
    from svg2ooxml.drawingml.bridges.resvg_gradient_transform import TransformClass

logger = logging.getLogger("svg2ooxml.drawingml.bridges.resvg_gradient_adapter")


def radial_gradient_to_paint(gradient: RadialGradient) -> RadialGradientPaint:
    """Convert a resvg radial gradient to IR paint, requesting raster fallback when needed."""

    context = _radial_transform_context(gradient)
    center = _gradient_center(gradient, use_raw_coordinates=context.use_raw_coordinates)
    radius = _gradient_radius(
        gradient,
        center=center,
        use_raw_coordinates=context.use_raw_coordinates,
    )
    focal_radius = _gradient_focal_radius(
        gradient,
        radius=radius,
        use_raw_coordinates=context.use_raw_coordinates,
    )
    focal_point = _gradient_focal_point(
        gradient,
        use_raw_coordinates=context.use_raw_coordinates,
    )

    return RadialGradientPaint(
        stops=gradient_stops_to_ir(gradient.stops),
        center=center,
        radius=radius,
        focal_point=focal_point,
        focal_radius=focal_radius,
        transform=context.transform_matrix,
        gradient_id=gradient_id_or_none(gradient.href),
        gradient_transform=gradient.transform,
        original_transform=None,
        had_transform_flag=context.had_transform,
        transform_class=context.transform_class,
        policy_decision=context.policy_decision,
        gradient_units=gradient.units,
        spread_method=gradient.spread_method,
    )


class _RadialTransformContext:
    def __init__(
        self,
        *,
        had_transform: bool,
        transform_class: TransformClass | None = None,
        policy_decision: str | None = None,
        use_raw_coordinates: bool = False,
        transform_matrix=None,
    ) -> None:
        self.had_transform = had_transform
        self.transform_class = transform_class
        self.policy_decision = policy_decision
        self.use_raw_coordinates = use_raw_coordinates
        self.transform_matrix = transform_matrix


def _radial_transform_context(gradient: RadialGradient) -> _RadialTransformContext:
    if gradient.transform is None:
        return _RadialTransformContext(had_transform=False)

    policy_decision, transform_class = decide_radial_policy(
        gradient.transform.a,
        gradient.transform.b,
        gradient.transform.c,
        gradient.transform.d,
    )
    context = _RadialTransformContext(
        had_transform=True,
        transform_class=transform_class,
        policy_decision=policy_decision,
    )

    if policy_decision == "vector_warn_mild_anisotropy":
        _log_mild_anisotropy(gradient, transform_class)
    elif policy_decision == "rasterize_nonuniform":
        _log_raster_fallback(gradient, transform_class)
        context.use_raw_coordinates = True
        context.transform_matrix = _matrix_to_numpy(gradient.transform)

    return context


def _log_mild_anisotropy(
    gradient: RadialGradient,
    transform_class: TransformClass,
) -> None:
    logger.debug(
        "Radial gradient has mild anisotropy (ratio=%.3f): "
        "Rendering as circle (approximate). "
        "Transform: [[%.3f, %.3f], [%.3f, %.3f]], "
        "Singular values: s1=%.3f, s2=%.3f, "
        "Gradient ID: %s",
        transform_class.ratio,
        gradient.transform.a,
        gradient.transform.c,
        gradient.transform.b,
        gradient.transform.d,
        transform_class.s1,
        transform_class.s2,
        gradient.href or "(none)",
    )


def _log_raster_fallback(
    gradient: RadialGradient,
    transform_class: TransformClass,
) -> None:
    raster_size = _calculate_raster_size(transform_class.s1, transform_class.s2)
    reason = (
        "shear"
        if transform_class.has_shear
        else f"non-uniform scale (ratio={transform_class.ratio:.3f})"
    )
    logger.info(
        "Radial gradient has %s: "
        "raster fallback requested. "
        "Transform: [[%.3f, %.3f], [%.3f, %.3f]], "
        "Singular values: s1=%.3f, s2=%.3f, "
        "Raster size would be: %dpx, "
        "Gradient ID: %s",
        reason,
        gradient.transform.a,
        gradient.transform.c,
        gradient.transform.b,
        gradient.transform.d,
        transform_class.s1,
        transform_class.s2,
        raster_size,
        gradient.href or "(none)",
    )


def _gradient_center(
    gradient: RadialGradient,
    *,
    use_raw_coordinates: bool,
) -> tuple[float, float]:
    if use_raw_coordinates:
        return (gradient.cx, gradient.cy)
    return _apply_matrix_to_point(gradient.cx, gradient.cy, gradient.transform)


def _gradient_radius(
    gradient: RadialGradient,
    *,
    center: tuple[float, float],
    use_raw_coordinates: bool,
) -> float:
    if gradient.transform is None or use_raw_coordinates:
        return gradient.r

    edge_point = _apply_matrix_to_point(
        gradient.cx + gradient.r,
        gradient.cy,
        gradient.transform,
    )
    dx = edge_point[0] - center[0]
    dy = edge_point[1] - center[1]
    return math.sqrt(dx * dx + dy * dy)


def _gradient_focal_point(
    gradient: RadialGradient,
    *,
    use_raw_coordinates: bool,
) -> tuple[float, float] | None:
    if (
        abs(gradient.fx - gradient.cx) <= 1e-6
        and abs(gradient.fy - gradient.cy) <= 1e-6
    ):
        return None
    if use_raw_coordinates:
        return (gradient.fx, gradient.fy)
    return _apply_matrix_to_point(gradient.fx, gradient.fy, gradient.transform)


def _gradient_focal_radius(
    gradient: RadialGradient,
    *,
    radius: float,
    use_raw_coordinates: bool,
) -> float | None:
    if gradient.fr <= 1e-6:
        return None
    if gradient.transform is None or use_raw_coordinates:
        return gradient.fr
    if abs(gradient.r) <= 1e-6:
        return None
    return abs(gradient.fr * radius / gradient.r)


__all__ = ["radial_gradient_to_paint"]
