"""Simplified feDisplacementMap filter primitive."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import DisplacementMapParameters, parse_displacement_map

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string


class DisplacementMapFilter(Filter):
    primitive_tags = ("feDisplacementMap",)
    filter_type = "displacement_map"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = parse_displacement_map(primitive)
        metadata = {
            "filter_type": self.filter_type,
            "scale": params.scale,
            "x_channel": params.x_channel,
            "y_channel": params.y_channel,
            "source": params.source_graphic,
            "map_source": params.displacement_map,
        }
        if abs(params.scale) < 1e-6:
            drawingml = self._placeholder_drawingml(params)
            metadata["strategy"] = "no_op"
            metadata["native_support"] = True
            return FilterResult(success=True, drawingml=drawingml, metadata=metadata)

        metadata["strategy"] = "emf_fallback"
        metadata["native_support"] = False
        return FilterResult(
            success=True,
            drawingml="",
            fallback="emf",
            metadata=metadata,
            warnings=["feDisplacementMap rendered via EMF fallback"],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _placeholder_drawingml(self, params: DisplacementMapParameters) -> str:
        # Note: XML comments not supported in lxml element building,
        # but this is just a placeholder anyway
        effectLst = a_elem("effectLst")
        a_sub(effectLst, "glow", rad="0")
        return to_string(effectLst)


__all__ = ["DisplacementMapFilter"]
