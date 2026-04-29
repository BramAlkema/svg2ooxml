"""Gradient service utilities."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.common.svg_refs import local_name, local_url_id, reference_id
from svg2ooxml.drawingml.bridges.resvg_paint_bridge import (
    GradientDescriptor,
    LinearGradientDescriptor,
    RadialGradientDescriptor,
)
from svg2ooxml.services.gradient_service_conversion import (
    GradientServiceConversionMixin,
)

from .gradient_processor import GradientAnalysis, GradientProcessor

if TYPE_CHECKING:  # pragma: no cover - import guarded for mypy
    from .conversion import ConversionServices


logger = logging.getLogger(__name__)


@dataclass
class GradientService(GradientServiceConversionMixin):
    """Lookup helper for gradients with simple inheritance resolution."""

    _descriptors: dict[str, GradientDescriptor] = field(default_factory=dict)
    _services: ConversionServices | None = None
    _processor: GradientProcessor | Any | None = None
    _conversion_cache: dict[str, str] = field(default_factory=dict)
    _policy_engine: Any | None = None
    _mesh_engine: Any | None = None
    _analysis_cache: dict[str, GradientAnalysis] = field(default_factory=dict)
    _materialized_elements: dict[str, etree._Element] = field(default_factory=dict)

    def bind_services(self, services: ConversionServices) -> None:
        self._services = services
        if self._policy_engine is None:
            self._policy_engine = services.resolve("policy_engine")
        if self._processor is None:
            self._processor = GradientProcessor()
        existing = services.resolve("gradients")
        if existing:
            self.update_definitions(existing)

    def update_definitions(
        self,
        gradients: Mapping[str, GradientDescriptor | etree._Element] | None,
    ) -> None:
        self._descriptors.clear()
        self._materialized_elements.clear()
        self._conversion_cache.clear()
        self._analysis_cache.clear()
        if not gradients:
            return
        for gradient_id, definition in gradients.items():
            descriptor = self._coerce_descriptor(gradient_id, definition)
            if descriptor is None:
                continue
            key = descriptor.gradient_id or gradient_id
            self._descriptors[key] = descriptor

    def get(self, gradient_id: str) -> GradientDescriptor | None:
        return self._descriptors.get(gradient_id)

    def require(self, gradient_id: str) -> GradientDescriptor:
        descriptor = self.get(gradient_id)
        if descriptor is None:
            raise KeyError(f"gradient {gradient_id!r} is not defined")
        return descriptor

    def ids(self) -> Iterable[str]:
        return tuple(self._descriptors.keys())

    def resolve_chain(
        self,
        gradient_id: str,
        *,
        include_self: bool = True,
    ) -> list[GradientDescriptor]:
        """Follow xlink:href chains to gather inherited gradient descriptors."""
        chain: list[GradientDescriptor] = []
        visited: set[str] = set()
        current_id = gradient_id
        while current_id and current_id not in visited:
            visited.add(current_id)
            descriptor = self.get(current_id)
            if descriptor is None:
                break
            if include_self or current_id != gradient_id:
                chain.append(descriptor)
            href = getattr(descriptor, "href", None)
            next_id = local_url_id(href)
            if next_id is None:
                break
            current_id = next_id
        return chain

    def clone(self) -> GradientService:
        clone = GradientService()
        clone._descriptors = dict(self._descriptors)
        clone._processor = self._processor
        clone._conversion_cache = dict(self._conversion_cache)
        clone._analysis_cache = dict(self._analysis_cache)
        clone._policy_engine = self._policy_engine
        clone._materialized_elements = dict(self._materialized_elements)
        return clone

    # ------------------------------------------------------------------ #
    # Processor integration                                              #
    # ------------------------------------------------------------------ #

    def set_processor(self, processor: Any) -> None:
        self._processor = processor

    @property
    def processor(self) -> Any | None:
        return self._processor

    def set_policy_engine(self, engine: Any | None) -> None:
        self._policy_engine = engine

    def analyse_gradient(self, gradient_id: str) -> GradientAnalysis | None:
        """Return cached analysis for ``gradient_id`` if one exists."""

        return self._analysis_cache.get(gradient_id)

    # ------------------------------------------------------------------ #
    # Registration & conversion helpers                                  #
    # ------------------------------------------------------------------ #

    def register_gradient(
        self,
        gradient_id: str,
        definition: GradientDescriptor | etree._Element,
    ) -> None:
        descriptor = self._coerce_descriptor(gradient_id, definition)
        if descriptor is None:
            return
        key = descriptor.gradient_id or gradient_id
        self._descriptors[key] = descriptor
        self._conversion_cache.pop(key, None)
        self._analysis_cache.pop(key, None)
        self._materialized_elements.pop(key, None)

    def get_gradient_content(self, gradient_id: str, context: Any | None = None) -> str | None:
        clean_id = reference_id(gradient_id) or ""

        cached = self._conversion_cache.get(clean_id)
        if cached is not None:
            return cached

        descriptor = self.get(clean_id)
        if descriptor is None:
            logger.debug("Gradient %s not registered", gradient_id)
            return None
        element = self._materialize_gradient(clean_id, descriptor)

        analysis: GradientAnalysis | None = None
        if self._processor is not None:
            try:
                analysis = self._processor.analyse(element, context=context)
                self._analysis_cache[clean_id] = analysis
            except Exception:  # pragma: no cover - defensive
                logger.debug("Gradient processor failed for %s", clean_id, exc_info=True)
                analysis = None

        gradient_type = (
            "linearGradient"
            if isinstance(descriptor, LinearGradientDescriptor)
            else "radialGradient"
            if isinstance(descriptor, RadialGradientDescriptor)
            else local_name(element.tag)
        )

        if gradient_type == "linearGradient":
            content = self._convert_linear_gradient(element, analysis)
        elif gradient_type == "radialGradient":
            content = self._convert_radial_gradient(element, analysis)
        elif gradient_type == "meshgradient":
            content = self._convert_mesh_gradient(element, analysis)
        else:
            content = f"<!-- svg2ooxml:unsupported gradient type={gradient_type} -->"

        self._conversion_cache[clean_id] = content
        return content

    def clear_cache(self) -> None:
        self._conversion_cache.clear()
        self._materialized_elements.clear()



__all__ = ["GradientService"]
