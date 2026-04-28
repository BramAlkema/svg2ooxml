"""Gradient paint metadata and fallback policy recording."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from svg2ooxml.core.styling.paint import (
    ensure_paint_policy,
    maybe_set_geometry_fallback,
)
from svg2ooxml.core.styling.style_helpers import (
    descriptor_stop_colors,
    matrix_tuple_is_identity,
)
from svg2ooxml.drawingml.bridges.resvg_paint_bridge import (
    GradientDescriptor,
    LinearGradientDescriptor,
    MeshGradientDescriptor,
)
from svg2ooxml.elements.gradient_processor import GradientComplexity
from svg2ooxml.policy.constants import FALLBACK_EMF
from svg2ooxml.services import ConversionServices

if TYPE_CHECKING:  # pragma: no cover - hint only
    from svg2ooxml.core.tracing import ConversionTracer


def get_gradient_processor(services: ConversionServices):
    processor = services.resolve("gradient_processor")
    if processor is None and services.gradient_service is not None:
        processor = getattr(services.gradient_service, "processor", None)
    return processor


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
    analysis_entry = _base_gradient_analysis(gradient_id, descriptor)
    processor = get_gradient_processor(services)
    analysis = _analyze_gradient_descriptor(
        processor, gradient_service, descriptor, context
    )

    colors_from_analysis = None
    color_stats = None
    if analysis is not None:
        colors_from_analysis, color_stats = _merge_processor_analysis(
            analysis_entry, analysis
        )

    _store_gradient_analysis(metadata, role, analysis_entry)

    paint_policy = ensure_paint_policy(metadata, role)
    _apply_gradient_policy(
        paint_policy=paint_policy,
        gradient_id=gradient_id,
        analysis_entry=analysis_entry,
        analysis=analysis,
        colors_from_analysis=colors_from_analysis,
        color_stats=color_stats,
        metadata=metadata,
        tracer=tracer,
    )
    _trace_gradient_decision(tracer, gradient_id, analysis_entry, paint_policy)


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

    _store_gradient_analysis(metadata, role, analysis_entry)

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


def _base_gradient_analysis(
    gradient_id: str,
    descriptor: GradientDescriptor,
) -> dict[str, Any]:
    descriptor_colors = descriptor_stop_colors(descriptor)
    gradient_kind = (
        "linear" if isinstance(descriptor, LinearGradientDescriptor) else "radial"
    )
    analysis_entry: dict[str, Any] = {
        "id": gradient_id,
        "type": gradient_kind,
        "stop_count": len(getattr(descriptor, "stops", ())),
        "powerpoint_compatible": True,
        "complexity": "unknown",
    }

    transform = getattr(descriptor, "transform", None)
    if isinstance(transform, tuple) and len(transform) == 6:
        analysis_entry["has_transforms"] = not matrix_tuple_is_identity(transform)

    if descriptor_colors:
        analysis_entry["colors_used"] = descriptor_colors

    return analysis_entry


def _analyze_gradient_descriptor(
    processor,
    gradient_service: Any,
    descriptor: GradientDescriptor,
    context: Any | None,
):
    if processor is None or gradient_service is None:
        return None
    try:
        gradient_element = gradient_service.as_element(descriptor)
    except Exception:  # pragma: no cover - defensive
        return None
    try:
        return processor.analyze_gradient_element(gradient_element, context)
    except Exception:  # pragma: no cover - defensive
        return None


def _merge_processor_analysis(
    analysis_entry: dict[str, Any],
    analysis,
) -> tuple[Any | None, Any | None]:
    analysis_entry["type"] = getattr(analysis, "gradient_type", analysis_entry["type"])
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
            "transform_complexity": getattr(metrics, "transform_complexity", None),
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

    return colors_from_analysis, color_stats


def _store_gradient_analysis(
    metadata: dict[str, Any],
    role: str,
    analysis_entry: dict[str, Any],
) -> None:
    metadata.setdefault("paint_analysis", {}).setdefault(role, {})["gradient"] = (
        analysis_entry
    )


def _apply_gradient_policy(
    *,
    paint_policy: dict[str, Any],
    gradient_id: str,
    analysis_entry: dict[str, Any],
    analysis,
    colors_from_analysis,
    color_stats,
    metadata: dict[str, Any],
    tracer: ConversionTracer | None,
) -> None:
    paint_policy.setdefault("type", "gradient")
    paint_policy.setdefault("id", gradient_id)
    paint_policy.setdefault("complexity", analysis_entry.get("complexity", "unknown"))

    palette_source = colors_from_analysis or analysis_entry.get("colors_used")
    if palette_source:
        paint_policy.setdefault("palette", list(palette_source))

    if isinstance(color_stats, dict):
        recommended_space = color_stats.get("recommended_space")
        if recommended_space:
            paint_policy.setdefault("recommended_color_space", recommended_space)

    if analysis is None:
        return

    complexity = getattr(analysis, "complexity", None)
    if complexity in {
        GradientComplexity.COMPLEX,
        GradientComplexity.UNSUPPORTED,
    }:
        paint_policy["suggest_fallback"] = FALLBACK_EMF
        maybe_set_geometry_fallback(metadata, FALLBACK_EMF, tracer)


def _trace_gradient_decision(
    tracer: ConversionTracer | None,
    gradient_id: str,
    analysis_entry: dict[str, Any],
    paint_policy: dict[str, Any],
) -> None:
    if tracer is None:
        return
    decision = (
        "emf" if paint_policy.get("suggest_fallback") == FALLBACK_EMF else "native"
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


__all__ = [
    "get_gradient_processor",
    "record_gradient_metadata",
    "record_mesh_gradient_metadata",
]
