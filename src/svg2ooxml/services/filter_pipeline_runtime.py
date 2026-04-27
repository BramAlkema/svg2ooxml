"""Optional filter pipeline loading helpers."""

from __future__ import annotations

ALLOWED_STRATEGIES = {
    "auto",
    "native",
    "native-if-neutral",
    "vector",
    "raster",
    "emf",
    "resvg",
    "resvg-only",
}


def load_filter_pipeline():
    try:
        from svg2ooxml.filters.planner import FilterPlanner
        from svg2ooxml.filters.renderer import FilterRenderer as FilterPipelineRenderer

        return FilterPlanner, FilterPipelineRenderer, None
    except Exception as full_error:  # pragma: no cover - optional dependency missing
        try:
            from svg2ooxml.filters.lightweight import (
                LightweightFilterPlanner as FilterPlanner,
            )
            from svg2ooxml.filters.lightweight import (
                LightweightFilterRenderer as FilterPipelineRenderer,
            )
        except Exception as fallback_error:  # pragma: no cover - defensive
            return None, None, fallback_error
        return FilterPlanner, FilterPipelineRenderer, full_error


def pipeline_warning_message(error: Exception | None) -> str:
    if error is None:
        return "optional filter pipeline dependencies are missing"
    return f"{type(error).__name__}: {error}"


__all__ = [
    "ALLOWED_STRATEGIES",
    "load_filter_pipeline",
    "pipeline_warning_message",
]
