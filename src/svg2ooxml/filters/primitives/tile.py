"""feTile filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult


@dataclass
class TileParams:
    input_name: str


class TileFilter(Filter):
    primitive_tags = ("feTile",)
    filter_type = "tile"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = self._parse_params(primitive)
        pipeline = context.pipeline_state or {}
        source = pipeline.get(params.input_name)
        metadata = {
            "filter_type": self.filter_type,
            "input": params.input_name,
        }
        if source is not None:
            metadata["source_metadata"] = dict(source.metadata or {})
            return FilterResult(
                success=True,
                drawingml=source.drawingml,
                fallback=source.fallback,
                metadata=metadata,
            )

        metadata["native_support"] = False
        metadata["fallback_reason"] = "unresolved_input"
        return FilterResult(
            success=True,
            drawingml="",
            fallback="emf",
            metadata=metadata,
            warnings=["feTile rendered via EMF fallback"],
        )

    def _parse_params(self, primitive: etree._Element) -> TileParams:
        name = primitive.get("in") or "SourceGraphic"
        return TileParams(input_name=name)


__all__ = ["TileFilter"]
