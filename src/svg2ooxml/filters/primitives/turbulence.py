"""Simplified feTurbulence filter primitive."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import parse_turbulence


class TurbulenceFilter(Filter):
    primitive_tags = ("feTurbulence",)
    filter_type = "turbulence"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = parse_turbulence(primitive)
        metadata = {
            "filter_type": self.filter_type,
            "base_frequency_x": params.base_frequency_x,
            "base_frequency_y": params.base_frequency_y,
            "num_octaves": params.num_octaves,
            "seed": params.seed,
            "turbulence_type": params.turbulence_type,
            "stitch_tiles": params.stitch_tiles,
            "native_support": False,
            "strategy": "emf_fallback",
        }
        return FilterResult(
            success=True,
            drawingml="",
            fallback="emf",
            metadata=metadata,
            warnings=["feTurbulence rendered via EMF fallback"],
        )


__all__ = ["TurbulenceFilter"]
