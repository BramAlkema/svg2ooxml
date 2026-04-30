"""Build IR gradient paints from resolved SVG gradient descriptors."""

from __future__ import annotations

from typing import Any

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D, parse_transform_list
from svg2ooxml.common.gradient_units import normalize_gradient_units
from svg2ooxml.core.styling.paint.gradient_resolution import (
    collect_gradient_stops,
    gradient_attr,
    resolve_gradient_length,
    resolve_gradient_point,
)
from svg2ooxml.core.styling.style_helpers import (
    apply_matrix_to_point,
    matrix2d_to_numpy,
)
from svg2ooxml.ir.paint import (
    GradientStop,
    LinearGradientPaint,
    RadialGradientPaint,
)
from svg2ooxml.services import ConversionServices


def build_gradient_paint(
    *,
    gradient_id: str,
    services: ConversionServices,
    element: etree._Element,
    opacity: float,
    context: Any | None,
    unit_converter,
) -> LinearGradientPaint | RadialGradientPaint | None:
    gradient_service = services.gradient_service
    if gradient_service is None:
        return None

    materialized_chain = _materialize_gradient_chain(gradient_id, gradient_service)
    if not materialized_chain:
        return None

    gradient_type = gradient_attr(materialized_chain, "__tag__")
    if gradient_type not in {"linearGradient", "radialGradient"}:
        return None

    stops = collect_gradient_stops(materialized_chain, opacity)
    if len(stops) < 2:
        return None

    gradient_units = normalize_gradient_units(
        gradient_attr(materialized_chain, "gradientUnits", default="objectBoundingBox")
    )
    spread_method = gradient_attr(materialized_chain, "spreadMethod", default="pad")
    transform_matrix = _parse_gradient_transform(materialized_chain)
    conversion = getattr(context, "conversion", None) if context else None

    if gradient_type == "linearGradient":
        return _build_linear_gradient_paint(
            gradient_id=gradient_id,
            chain=materialized_chain,
            stops=stops,
            gradient_units=gradient_units,
            spread_method=spread_method,
            transform_matrix=transform_matrix,
            conversion=conversion,
            unit_converter=unit_converter,
        )

    return _build_radial_gradient_paint(
        gradient_id=gradient_id,
        chain=materialized_chain,
        stops=stops,
        gradient_units=gradient_units,
        spread_method=spread_method,
        transform_matrix=transform_matrix,
        conversion=conversion,
        unit_converter=unit_converter,
    )


def _materialize_gradient_chain(
    gradient_id: str,
    gradient_service,
) -> list[etree._Element]:
    descriptor_chain = gradient_service.resolve_chain(gradient_id, include_self=True)
    if not descriptor_chain:
        descriptor = gradient_service.get(gradient_id)
        if descriptor is None:
            return []
        descriptor_chain = [descriptor]
    return [gradient_service.as_element(descriptor) for descriptor in descriptor_chain]


def _parse_gradient_transform(chain: list[etree._Element]) -> Matrix2D | None:
    gradient_transform = gradient_attr(chain, "gradientTransform")
    if not gradient_transform:
        return None
    try:
        return parse_transform_list(gradient_transform)
    except Exception:
        return None


def _build_linear_gradient_paint(
    *,
    gradient_id: str,
    chain: list[etree._Element],
    stops: list[GradientStop],
    gradient_units: str,
    spread_method: str | None,
    transform_matrix: Matrix2D | None,
    conversion,
    unit_converter,
) -> LinearGradientPaint:
    start = resolve_gradient_point(
        chain,
        "x1",
        "y1",
        default=("0%", "0%"),
        units=gradient_units,
        conversion=conversion,
        axis_defaults=("x", "y"),
        unit_converter=unit_converter,
    )
    end = resolve_gradient_point(
        chain,
        "x2",
        "y2",
        default=("100%", "0%"),
        units=gradient_units,
        conversion=conversion,
        axis_defaults=("x", "y"),
        unit_converter=unit_converter,
    )

    if transform_matrix is not None:
        start = apply_matrix_to_point(transform_matrix, start)
        end = apply_matrix_to_point(transform_matrix, end)

    return LinearGradientPaint(
        stops=stops,
        start=start,
        end=end,
        transform=matrix2d_to_numpy(transform_matrix),
        gradient_id=gradient_id,
        gradient_units=gradient_units,
        spread_method=spread_method,
    )


def _build_radial_gradient_paint(
    *,
    gradient_id: str,
    chain: list[etree._Element],
    stops: list[GradientStop],
    gradient_units: str,
    spread_method: str | None,
    transform_matrix: Matrix2D | None,
    conversion,
    unit_converter,
) -> RadialGradientPaint:
    center = resolve_gradient_point(
        chain,
        "cx",
        "cy",
        default=("50%", "50%"),
        units=gradient_units,
        conversion=conversion,
        axis_defaults=("x", "y"),
        unit_converter=unit_converter,
    )
    radius = resolve_gradient_length(
        chain,
        "r",
        default="50%",
        units=gradient_units,
        conversion=conversion,
        axis="x",
        unit_converter=unit_converter,
    )
    focal_radius = resolve_gradient_length(
        chain,
        "fr",
        default="0%",
        units=gradient_units,
        conversion=conversion,
        axis="x",
        unit_converter=unit_converter,
    )
    if gradient_units == "userSpaceOnUse":
        default_focal = (str(center[0]), str(center[1]))
    else:
        default_focal = (f"{center[0] * 100}%", f"{center[1] * 100}%")
    focal = resolve_gradient_point(
        chain,
        "fx",
        "fy",
        default=default_focal,
        units=gradient_units,
        conversion=conversion,
        axis_defaults=("x", "y"),
        unit_converter=unit_converter,
    )

    if transform_matrix is not None:
        center = apply_matrix_to_point(transform_matrix, center)
        focal = apply_matrix_to_point(transform_matrix, focal)

    return RadialGradientPaint(
        stops=stops,
        center=center,
        radius=radius,
        focal_point=focal,
        focal_radius=focal_radius if focal_radius > 1e-6 else None,
        transform=matrix2d_to_numpy(transform_matrix),
        gradient_id=gradient_id,
        gradient_units=gradient_units,
        spread_method=spread_method,
    )


__all__ = ["build_gradient_paint"]
