"""Core filter abstractions shared by svg2ooxml."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

from lxml import etree


@dataclass
class FilterContext:
    """Carries shared state when evaluating filter primitives."""

    filter_element: etree._Element
    services: Any | None = None
    policy_engine: Any | None = None
    viewport: Dict[str, float] | None = None
    options: Dict[str, Any] = field(default_factory=dict)
    primitive: etree._Element | None = None
    pipeline_state: Dict[str, "FilterResult"] | None = None

    def with_primitive(self, primitive: etree._Element) -> "FilterContext":
        """Return a child context referencing the current primitive."""

        return FilterContext(
            filter_element=self.filter_element,
            services=self.services,
            policy_engine=self.policy_engine,
            viewport=self.viewport,
            options=dict(self.options),
            primitive=primitive,
            pipeline_state=self.pipeline_state,
        )


@dataclass
class FilterResult:
    """Outcome of processing a single SVG filter primitive."""

    success: bool
    drawingml: str | None = None
    fallback: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: Iterable[str] = field(default_factory=list)
    result_name: Optional[str] = None

    def is_success(self) -> bool:
        return self.success


class Filter(ABC):
    """Abstract base class for SVG filter primitive processors."""

    primitive_tags: tuple[str, ...] = ()
    filter_type: str = "generic"

    def __init__(self) -> None:
        if not self.primitive_tags:
            raise ValueError("Filters must declare at least one primitive tag")

    def matches(self, primitive: etree._Element, context: FilterContext) -> bool:
        """Return True if this filter can process the primitive."""

        return self._local_name(getattr(primitive, "tag", "")) in self.primitive_tags and self.validate(
            primitive, context
        )

    def validate(self, primitive: etree._Element, context: FilterContext) -> bool:
        """Optional validation hook."""

        return True

    @abstractmethod
    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        """Convert the primitive to DrawingML output."""

    @staticmethod
    def _local_name(tag: str | None) -> str:
        if not tag:
            return ""
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag


__all__ = ["Filter", "FilterContext", "FilterResult"]
