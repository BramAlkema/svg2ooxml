"""Public facade for filter planning and execution."""

from __future__ import annotations

from svg2ooxml.render.filters_executor import apply_filter
from svg2ooxml.render.filters_model import (
    REGISTERED_FILTER_PRIMITIVES,
    RESVG_SUPPORTED_PRIMITIVES,
    UNSUPPORTED_FILTER_PRIMITIVES,
    ComponentTransferFunction,
    ComponentTransferPlan,
    FilterPlan,
    FilterPrimitivePlan,
    PrimitiveUnitScale,
    UnsupportedPrimitiveError,
)
from svg2ooxml.render.filters_planner import plan_filter

__all__ = [
    "ComponentTransferFunction",
    "ComponentTransferPlan",
    "FilterPlan",
    "FilterPrimitivePlan",
    "PrimitiveUnitScale",
    "REGISTERED_FILTER_PRIMITIVES",
    "RESVG_SUPPORTED_PRIMITIVES",
    "UNSUPPORTED_FILTER_PRIMITIVES",
    "UnsupportedPrimitiveError",
    "apply_filter",
    "plan_filter",
]
