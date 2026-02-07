"""Marker service helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from svg2ooxml.core.traversal.markers import MarkerDefinition, parse_marker_definition

XLINK_HREF = "{http://www.w3.org/1999/xlink}href"

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from lxml import etree

    from .conversion import ConversionServices


@dataclass
class MarkerService:
    """Provides access to marker definitions."""

    _markers: dict[str, etree._Element] = field(default_factory=dict)
    _definitions: dict[str, MarkerDefinition] = field(default_factory=dict)
    _services: ConversionServices | None = None

    def bind_services(self, services: ConversionServices) -> None:
        self._services = services
        existing = services.resolve("markers")
        if existing:
            self.update_definitions(existing)

    def update_definitions(
        self,
        markers: Mapping[str, etree._Element] | None,
    ) -> None:
        self._markers = dict(markers or {})
        self._definitions.clear()

    def get(self, marker_id: str) -> etree._Element | None:
        return self._markers.get(marker_id)

    def get_definition(self, marker_id: str) -> MarkerDefinition | None:
        definition = self._definitions.get(marker_id)
        if definition is not None:
            return definition
        element = self.get(marker_id)
        if element is None:
            return None
        try:
            definition = parse_marker_definition(element)
        except ValueError:
            return None
        self._definitions[marker_id] = definition
        return definition

    def require(self, marker_id: str) -> etree._Element:
        element = self.get(marker_id)
        if element is None:
            raise KeyError(f"marker {marker_id!r} is not defined")
        return element

    def ids(self) -> Iterable[str]:
        return tuple(self._markers.keys())

    def resolve_chain(
        self,
        marker_id: str,
        *,
        include_self: bool = True,
    ) -> list[etree._Element]:
        """Resolve marker inheritance via xlink:href chains."""
        chain: list[etree._Element] = []
        visited: set[str] = set()
        current = marker_id
        while current and current not in visited:
            visited.add(current)
            element = self.get(current)
            if element is None:
                break
            if include_self or current != marker_id:
                chain.append(element)
            href = element.get("href") or element.get(XLINK_HREF)
            if not href or not href.startswith("#"):
                break
            current = href[1:]
        return chain

    def clone(self) -> MarkerService:
        clone = MarkerService()
        clone._markers = dict(self._markers)
        clone._definitions = {key: value.clone() for key, value in self._definitions.items()}
        return clone


__all__ = ["MarkerService"]
