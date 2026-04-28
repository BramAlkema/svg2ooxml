"""Filter definition storage and materialization helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.common.svg_refs import reference_id
from svg2ooxml.filters.resvg_bridge import (
    ResolvedFilter,
    build_filter_element,
    resolve_filter_element,
)


class FilterDefinitionMixin:
    """Manage registered SVG filter descriptors."""

    def update_definitions(
        self,
        filters: Mapping[str, ResolvedFilter | etree._Element] | None,
    ) -> None:
        """Replace the known filter definitions."""
        self._descriptors.clear()
        self._materialized_filters.clear()
        for filter_id, definition in (filters or {}).items():
            lookup_id = self._lookup_filter_id(filter_id)
            if lookup_id is None:
                continue
            descriptor = self._coerce_descriptor(lookup_id, definition)
            if descriptor is None:
                continue
            key = self._lookup_filter_id(descriptor.filter_id) or lookup_id
            self._descriptors[key] = descriptor

    def register_filter(
        self,
        filter_id: str,
        definition: ResolvedFilter | etree._Element,
    ) -> None:
        """Register a single filter definition."""
        lookup_id = self._lookup_filter_id(filter_id)
        if not lookup_id:
            raise ValueError("filter id must be non-empty")
        descriptor = self._coerce_descriptor(lookup_id, definition)
        if descriptor is None:
            return
        key = self._lookup_filter_id(descriptor.filter_id) or lookup_id
        self._descriptors[key] = descriptor
        self._materialized_filters.pop(key, None)

    def get(self, filter_id: str) -> ResolvedFilter | None:
        """Return the stored filter descriptor if known."""
        lookup_id = self._lookup_filter_id(filter_id)
        if lookup_id is None:
            return None
        return self._descriptors.get(lookup_id)

    def require(self, filter_id: str) -> ResolvedFilter:
        """Return the filter descriptor or raise if missing."""
        element = self.get(filter_id)
        if element is None:
            raise KeyError(f"filter {filter_id!r} is not defined")
        return element

    def ids(self) -> Iterable[str]:
        """Iterate over registered filter ids."""
        return tuple(self._descriptors.keys())

    def get_filter_content(
        self,
        filter_id: str,
        *,
        context: Any | None = None,
    ) -> str | None:
        """Return DrawingML content for the requested filter reference."""
        lookup_id = self._lookup_filter_id(filter_id)
        if lookup_id is None:
            return None
        descriptor = self.get(lookup_id)
        if descriptor is None:
            return None
        element = self._materialize_filter(lookup_id, descriptor)
        try:
            return etree.tostring(element, encoding="unicode")
        except Exception:  # pragma: no cover - defensive
            self._logger.debug("Failed to serialise filter %s", filter_id, exc_info=True)
            return None

    def _materialize_filter(
        self,
        filter_id: str,
        descriptor: ResolvedFilter,
    ) -> etree._Element:
        cached = self._materialized_filters.get(filter_id)
        if cached is not None:
            return deepcopy(cached)
        element = build_filter_element(descriptor)
        self._materialized_filters[filter_id] = element
        return deepcopy(element)

    def _coerce_descriptor(
        self,
        filter_id: str,
        definition: ResolvedFilter | etree._Element,
    ) -> ResolvedFilter | None:
        if isinstance(definition, ResolvedFilter):
            descriptor = definition
        elif isinstance(definition, etree._Element):
            descriptor = resolve_filter_element(definition)
        else:
            self._logger.debug(
                "Unsupported filter definition type for %s: %r",
                filter_id,
                type(definition),
            )
            return None
        if not descriptor.filter_id:
            descriptor = replace(descriptor, filter_id=filter_id)
        return descriptor

    @staticmethod
    def _lookup_filter_id(filter_ref: str | None) -> str | None:
        return reference_id(filter_ref)


__all__ = ["FilterDefinitionMixin"]
