"""Filter planning helpers for resvg and descriptor fallbacks."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from svg2ooxml.filters import planner_geometry as _planner_geometry
from svg2ooxml.filters.base import FilterContext as FilterContext
from svg2ooxml.filters.base import FilterResult as FilterResult
from svg2ooxml.filters.planner_geometry import ResvgGeometryMixin
from svg2ooxml.filters.planner_neutral import NeutralPrimitiveMixin
from svg2ooxml.filters.planner_payload import DescriptorPayloadMixin
from svg2ooxml.filters.planner_policy import PolicyPlanningMixin
from svg2ooxml.filters.planner_summary import PlanSummaryMixin
from svg2ooxml.filters.resvg_bridge import (
    FilterPrimitiveDescriptor as FilterPrimitiveDescriptor,
)
from svg2ooxml.filters.resvg_bridge import ResolvedFilter as ResolvedFilter
from svg2ooxml.filters.resvg_bridge import build_filter_node
from svg2ooxml.render.filters import FilterPlan as FilterPlan
from svg2ooxml.render.filters import plan_filter
from svg2ooxml.render.rasterizer import Viewport as Viewport

_MAX_RESVG_VIEWPORT_DIMENSION_PX = _planner_geometry._MAX_RESVG_VIEWPORT_DIMENSION_PX
_MAX_RESVG_VIEWPORT_PIXELS = _planner_geometry._MAX_RESVG_VIEWPORT_PIXELS


class FilterPlanner(
    PlanSummaryMixin,
    NeutralPrimitiveMixin,
    ResvgGeometryMixin,
    PolicyPlanningMixin,
    DescriptorPayloadMixin,
):
    """Plan resvg filter execution and descriptor fallbacks."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    def build_resvg_plan(
        self,
        descriptor: ResolvedFilter,
        *,
        options: Mapping[str, Any] | None = None,
    ) -> FilterPlan | None:
        try:
            filter_node = build_filter_node(descriptor)
        except Exception:  # pragma: no cover - defensive
            self._logger.debug("Failed to construct filter node", exc_info=True)
            return None
        return plan_filter(filter_node, options=options)


__all__ = ["FilterPlanner"]
