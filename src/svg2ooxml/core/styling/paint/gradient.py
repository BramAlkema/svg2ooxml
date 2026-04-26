"""Gradient paint resolution — extracted from StyleExtractor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D, parse_transform_list
from svg2ooxml.common.gradient_units import (
    normalize_gradient_units,
    parse_gradient_coordinate,
)
from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.core.styling.paint import (
    ensure_paint_policy,
    maybe_set_geometry_fallback,
)
from svg2ooxml.core.styling.style_helpers import (
    apply_matrix_to_point,
    descriptor_stop_colors,
    matrix2d_to_numpy,
    matrix_tuple_is_identity,
    parse_offset,
    parse_stop_color,
)
from svg2ooxml.drawingml.bridges.resvg_paint_bridge import (
    GradientDescriptor,
    LinearGradientDescriptor,
    MeshGradientDescriptor,
)
from svg2ooxml.elements.gradient_processor import GradientComplexity
from svg2ooxml.ir.paint import (
    GradientStop,
    LinearGradientPaint,
    RadialGradientPaint,
)
from svg2ooxml.policy.constants import FALLBACK_EMF
from svg2ooxml.services import ConversionServices

if TYPE_CHECKING:  # pragma: no cover - hint only
    from svg2ooxml.core.tracing import ConversionTracer


def get_gradient_processor(services: ConversionServices):
    processor = services.resolve("gradient_processor")
    if processor is None and services.gradient_service is not None:
        processor = getattr(services.gradient_service, "processor", None)
    return processor


def gradient_attr(
    chain: list[etree._Element],
    attribute: str,
    *,
    default: str | None = None,
) -> str | None:
    if attribute == "__tag__":
        return local_name(chain[0].tag)
    for element in chain:
        value = element.get(attribute)
        if value is not None:
            return value
    return default


def collect_gradient_stops(
    chain: list[etree._Element],
    opacity: float,
) -> list[GradientStop]:
    for element in chain:
        stops = list(element.findall(".//{http://www.w3.org/2000/svg}stop"))
        if not stops:
            stops = list(element.findall(".//stop"))
        if stops:
            parsed = parse_stops(stops, opacity)
            if len(parsed) == 1:
                first = parsed[0]
                return [
                    GradientStop(offset=0.0, rgb=first.rgb, opacity=first.opacity),
                    GradientStop(offset=1.0, rgb=first.rgb, opacity=first.opacity),
                ]
            return parsed
    return []


def parse_stops(
    stops: list[etree._Element],
    opacity: float,
) -> list[GradientStop]:
    parsed: list[GradientStop] = []
    for stop in stops:
        offset_str = stop.get("offset", "0")
        offset = parse_offset(offset_str)
        color, stop_opacity = parse_stop_color(stop)
        total_opacity = max(0.0, min(1.0, stop_opacity * opacity))
        parsed.append(GradientStop(offset=offset, rgb=color, opacity=total_opacity))
    parsed.sort(key=lambda stop: stop.offset)
    return parsed


def resolve_gradient_point(
    chain: list[etree._Element],
    attr_x: str,
    attr_y: str,
    *,
    default: tuple[str, str] | None,
    units: str,
    conversion,
    axis_defaults: tuple[str, str],
    unit_converter,
) -> tuple[float, float]:
    x_value = gradient_attr(
        chain, attr_x, default=default[0] if default else None
    )
    y_value = gradient_attr(
        chain, attr_y, default=default[1] if default else None
    )
    return (
        resolve_gradient_length(
            chain, attr_x, x_value, units, conversion, axis_defaults[0],
            unit_converter=unit_converter,
        ),
        resolve_gradient_length(
            chain, attr_y, y_value, units, conversion, axis_defaults[1],
            unit_converter=unit_converter,
        ),
    )


def resolve_gradient_length(
    chain: list[etree._Element],
    attribute: str,
    default: str | None,
    units: str,
    conversion,
    axis: str,
    *,
    unit_converter=None,
) -> float:
    value = gradient_attr(chain, attribute, default=default)
    if value is None:
        return 0.0
    return parse_gradient_coordinate(
        value,
        units=units,
        context=conversion,
        axis=axis,
        default=default or "0",
        unit_converter=unit_converter,
    )


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
    descriptor_chain = gradient_service.resolve_chain(
        gradient_id, include_self=True
    )
    if not descriptor_chain:
        descriptor = gradient_service.get(gradient_id)
        if descriptor is None:
            return None
        descriptor_chain = [descriptor]

    materialized_chain = [
        gradient_service.as_element(descriptor) for descriptor in descriptor_chain
    ]

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
    gradient_transform = gradient_attr(
        materialized_chain, "gradientTransform"
    )
    transform_matrix: Matrix2D | None = None
    if gradient_transform:
        try:
            transform_matrix = parse_transform_list(gradient_transform)
        except Exception:
            transform_matrix = None

    conversion = getattr(context, "conversion", None) if context else None

    if gradient_type == "linearGradient":
        start = resolve_gradient_point(
            materialized_chain,
            "x1",
            "y1",
            default=("0%", "0%"),
            units=gradient_units,
            conversion=conversion,
            axis_defaults=("x", "y"),
            unit_converter=unit_converter,
        )
        end = resolve_gradient_point(
            materialized_chain,
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

        transform_np = matrix2d_to_numpy(transform_matrix)
        return LinearGradientPaint(
            stops=stops,
            start=start,
            end=end,
            transform=transform_np,
            gradient_id=gradient_id,
            gradient_units=gradient_units,
            spread_method=spread_method,
        )

    # radial gradient
    center = resolve_gradient_point(
        materialized_chain,
        "cx",
        "cy",
        default=("50%", "50%"),
        units=gradient_units,
        conversion=conversion,
        axis_defaults=("x", "y"),
        unit_converter=unit_converter,
    )
    radius = resolve_gradient_length(
        materialized_chain,
        "r",
        default="50%",
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
        materialized_chain,
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
        if focal is not None:
            focal = apply_matrix_to_point(transform_matrix, focal)

    transform_np = matrix2d_to_numpy(transform_matrix)
    return RadialGradientPaint(
        stops=stops,
        center=center,
        radius=radius,
        focal_point=focal,
        transform=transform_np,
        gradient_id=gradient_id,
        gradient_units=gradient_units,
        spread_method=spread_method,
    )


def record_gradient_metadata(
    *,
    gradient_id: str,
    descriptor: GradientDescriptor,
    gradient_service: Any,
    services: ConversionServices,
    metadata: dict[str, Any],
    role: str,
    context: Any | None,
    tracer: ConversionTracer | None,
) -> None:
    stop_count = len(getattr(descriptor, "stops", ()))
    descriptor_colors = descriptor_stop_colors(descriptor)
    gradient_kind = (
        "linear" if isinstance(descriptor, LinearGradientDescriptor) else "radial"
    )
    analysis_entry: dict[str, Any] = {
        "id": gradient_id,
        "type": gradient_kind,
        "stop_count": stop_count,
        "powerpoint_compatible": True,
        "complexity": "unknown",
    }

    transform = getattr(descriptor, "transform", None)
    if isinstance(transform, tuple) and len(transform) == 6:
        analysis_entry["has_transforms"] = not matrix_tuple_is_identity(transform)

    if descriptor_colors:
        analysis_entry["colors_used"] = descriptor_colors

    processor = get_gradient_processor(services)
    analysis = None
    if processor is not None and gradient_service is not None:
        try:
            gradient_element = gradient_service.as_element(descriptor)
        except Exception:  # pragma: no cover - defensive
            gradient_element = None
        if gradient_element is not None:
            try:
                analysis = processor.analyze_gradient_element(
                    gradient_element, context
                )
            except Exception:  # pragma: no cover - defensive
                analysis = None

    colors_from_analysis = None
    color_stats = None
    if analysis is not None:
        analysis_entry["type"] = getattr(
            analysis, "gradient_type", analysis_entry["type"]
        )
        complexity_attr = getattr(analysis, "complexity", None)
        if complexity_attr is not None:
            analysis_entry["complexity"] = getattr(
                complexity_attr, "value", str(complexity_attr)
            )
        stop_count_attr = getattr(analysis, "stop_count", None)
        if stop_count_attr is not None:
            analysis_entry["stop_count"] = stop_count_attr
        has_transform_attr = getattr(analysis, "has_transforms", None)
        if has_transform_attr is not None:
            analysis_entry["has_transforms"] = has_transform_attr
        analysis_entry["powerpoint_compatible"] = getattr(
            analysis, "powerpoint_compatible", True
        )

        optimizations = getattr(analysis, "optimization_opportunities", None)
        if optimizations:
            analysis_entry["optimizations"] = [
                getattr(opt, "value", str(opt)) for opt in optimizations
            ]

        metrics = getattr(analysis, "metrics", None)
        if metrics is not None:
            analysis_entry["metrics"] = {
                "stop_count": getattr(metrics, "stop_count", None),
                "color_complexity": getattr(metrics, "color_complexity", None),
                "transform_complexity": getattr(
                    metrics, "transform_complexity", None
                ),
                "memory_usage": getattr(metrics, "memory_usage", None),
                "processing_time": getattr(metrics, "processing_time", None),
            }

        colors_from_analysis = getattr(analysis, "colors_used", None)
        if colors_from_analysis:
            analysis_entry["colors_used"] = list(colors_from_analysis)

        color_spaces = getattr(analysis, "color_spaces_used", None)
        if color_spaces:
            analysis_entry["color_spaces_used"] = list(color_spaces)

        color_stats = getattr(analysis, "color_statistics", None)
        if isinstance(color_stats, dict) and color_stats:
            analysis_entry["color_statistics"] = color_stats

    metadata.setdefault("paint_analysis", {}).setdefault(role, {})[
        "gradient"
    ] = analysis_entry

    paint_policy = ensure_paint_policy(metadata, role)
    paint_policy.setdefault("type", "gradient")
    paint_policy.setdefault("id", gradient_id)
    paint_policy.setdefault(
        "complexity", analysis_entry.get("complexity", "unknown")
    )

    palette_source = colors_from_analysis or analysis_entry.get("colors_used")
    if palette_source:
        paint_policy.setdefault("palette", list(palette_source))

    if isinstance(color_stats, dict):
        recommended_space = color_stats.get("recommended_space")
        if recommended_space:
            paint_policy.setdefault("recommended_color_space", recommended_space)

    if analysis is not None:
        complexity = getattr(analysis, "complexity", None)
        # Keep gradient fallback decisions tied to demonstrated structural complexity.
        # The processor's generic "powerpoint_compatible" flag is conservative and
        # marks several supported features (e.g. spreadMethod/gradientUnits) as
        # incompatible, which can force unnecessary EMF fallback.
        if complexity in {
            GradientComplexity.COMPLEX,
            GradientComplexity.UNSUPPORTED,
        }:
            paint_policy["suggest_fallback"] = FALLBACK_EMF
            maybe_set_geometry_fallback(metadata, FALLBACK_EMF, tracer)

    if tracer is not None:
        decision = (
            "emf"
            if paint_policy.get("suggest_fallback") == FALLBACK_EMF
            else "native"
        )
        tracer.record_paint_decision(
            paint_type="gradient",
            paint_id=gradient_id,
            decision=decision,
            metadata={
                "analysis": analysis_entry,
                "policy": paint_policy,
            },
        )


def record_mesh_gradient_metadata(
    *,
    gradient_id: str,
    descriptor: MeshGradientDescriptor,
    services: ConversionServices,
    metadata: dict[str, Any],
    role: str,
    context: Any | None,
    tracer: ConversionTracer | None,
) -> None:
    analysis_entry: dict[str, Any] = {
        "id": gradient_id,
        "type": "mesh",
        "mesh_rows": descriptor.rows,
        "mesh_columns": descriptor.columns,
        "patch_count": descriptor.patch_count,
        "stop_count": descriptor.stop_count,
        "powerpoint_compatible": False,
    }
    if descriptor.colors:
        analysis_entry["colors_used"] = list(descriptor.colors)

    metadata.setdefault("paint_analysis", {}).setdefault(role, {})[
        "gradient"
    ] = analysis_entry

    paint_policy = ensure_paint_policy(metadata, role)
    paint_policy.setdefault("type", "gradient")
    paint_policy.setdefault("id", gradient_id)
    paint_policy["gradient_kind"] = "mesh"
    paint_policy["suggest_fallback"] = FALLBACK_EMF
    paint_policy["patch_count"] = descriptor.patch_count
    maybe_set_geometry_fallback(metadata, FALLBACK_EMF, tracer)

    if tracer is not None:
        tracer.record_paint_decision(
            paint_type="gradient",
            paint_id=gradient_id,
            decision="emf",
            metadata={
                "mesh_rows": descriptor.rows,
                "mesh_columns": descriptor.columns,
                "patch_count": descriptor.patch_count,
            },
        )
