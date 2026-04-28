"""Filter service scaffolding mirroring svg2pptx architecture."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.drawingml.emf_primitives import PaletteResolver
from svg2ooxml.filters.registry import FilterRegistry
from svg2ooxml.filters.resvg_bridge import ResolvedFilter
from svg2ooxml.services.filter_pipeline_runtime import (
    load_filter_pipeline as _load_filter_pipeline,  # noqa: F401
)
from svg2ooxml.services.filter_pipeline_runtime import (
    pipeline_warning_message as _pipeline_warning_message,  # noqa: F401
)
from svg2ooxml.services.filter_policy_runtime import FilterPolicyRuntimeMixin
from svg2ooxml.services.filter_render_runtime import FilterRenderRuntimeMixin
from svg2ooxml.services.filter_service_definitions import FilterDefinitionMixin
from svg2ooxml.services.filter_service_pipeline import (
    ALLOWED_STRATEGIES,
    FilterServicePipelineMixin,
)
from svg2ooxml.services.filter_service_resolution import FilterResolutionMixin

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.drawingml.raster_adapter import RasterAdapter
    from svg2ooxml.filters.planner import FilterPlanner
    from svg2ooxml.filters.renderer import FilterRenderer as FilterPipelineRenderer

    from .conversion import ConversionServices


class FilterService(
    FilterPolicyRuntimeMixin,
    FilterRenderRuntimeMixin,
    FilterDefinitionMixin,
    FilterServicePipelineMixin,
    FilterResolutionMixin,
):
    """Manage SVG filter definitions and provide conversion hooks."""

    def __init__(
        self,
        *,
        policy_engine: Any | None = None,
        registry: FilterRegistry | None = None,
        logger: logging.Logger | None = None,
        palette_resolver: PaletteResolver | None = None,
        raster_adapter: RasterAdapter | None = None,
    ) -> None:
        self._descriptors: dict[str, ResolvedFilter] = {}
        self._materialized_filters: dict[str, etree._Element] = {}
        self._services: ConversionServices | None = None
        self._policy_engine = policy_engine
        self._registry = registry or self._create_registry()
        self._logger = logger or logging.getLogger(__name__)
        self._strategy: str = "auto"
        self._palette_resolver: PaletteResolver | None = palette_resolver
        self._raster_adapter = raster_adapter
        self._planner: FilterPlanner | None = None
        self._renderer: FilterPipelineRenderer | None = None
        self._pipeline_error: Exception | None = None
        self._pipeline_warned = False
        self._runtime_capability: str = "pending"

    @property
    def policy_engine(self) -> Any | None:
        return self._policy_engine

    def set_policy_engine(self, engine: Any | None) -> None:
        """Update the policy engine used for filter evaluation."""

        self._policy_engine = engine

    @property
    def registry(self) -> FilterRegistry | None:
        return self._registry

    @property
    def runtime_capability(self) -> str:
        return self._runtime_capability


__all__ = ["ALLOWED_STRATEGIES", "FilterService"]
