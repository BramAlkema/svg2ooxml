"""Core filter abstractions shared by svg2ooxml."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from lxml import etree

if TYPE_CHECKING:
    from svg2ooxml.telemetry import RenderTracer


@dataclass
class FilterContext:
    """Carries shared state when evaluating filter primitives."""

    filter_element: etree._Element
    services: Any | None = None
    policy_engine: Any | None = None
    viewport: dict[str, float] | None = None
    options: dict[str, Any] = field(default_factory=dict)
    primitive: etree._Element | None = None
    pipeline_state: dict[str, FilterResult] | None = None
    tracer: RenderTracer | None = None

    @property
    def policy(self) -> dict[str, Any]:
        """Return the policy sub-dict from options, defaulting to empty."""
        if isinstance(self.options, dict):
            return self.options.get("policy") or {}
        return {}

    def with_primitive(self, primitive: etree._Element) -> FilterContext:
        """Return a child context referencing the current primitive."""

        return FilterContext(
            filter_element=self.filter_element,
            services=self.services,
            policy_engine=self.policy_engine,
            viewport=self.viewport,
            options=dict(self.options),
            primitive=primitive,
            pipeline_state=self.pipeline_state,
            tracer=self.tracer,
        )


@dataclass
class FilterResult:
    """Outcome of processing a single SVG filter primitive."""

    success: bool
    drawingml: str | None = None
    fallback: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: Iterable[str] = field(default_factory=list)
    result_name: str | None = None

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


def stitch_blip_transforms(
    metadata: dict[str, Any],
    transforms: list[dict[str, object]],
) -> None:
    """Attach blip color-transform candidates to filter metadata."""
    if transforms:
        metadata["native_color_transform_context"] = "blip"
        metadata["blip_color_transforms"] = transforms


__all__ = ["Filter", "FilterContext", "FilterResult", "stitch_blip_transforms"]
