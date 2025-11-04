"""Color matrix filter primitive."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string


@dataclass
class ColorMatrixParams:
    matrix_type: str
    values: List[float]


class ColorMatrixFilter(Filter):
    primitive_tags = ("feColorMatrix",)
    filter_type = "color_matrix"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = self._parse_parameters(primitive)
        drawingml = self._to_drawingml(params)
        raw_values = (primitive.get("values") or "").strip()
        fallback = None
        metadata = {
            "filter_type": self.filter_type,
            "matrix_type": params.matrix_type,
            "value_count": len(params.values),
            "matrix_source": raw_values,
        }
        if params.matrix_type == "matrix":
            values_list = list(params.values)
            if not values_list and raw_values:
                values_list = self._parse_floats(raw_values)
            metadata["values"] = values_list
            metadata["value_count"] = len(values_list)
            return FilterResult(
                success=True,
                drawingml="",
                fallback="emf",
                metadata=metadata,
                warnings=["feColorMatrix(matrix) rendered via EMF fallback"],
            )
        return FilterResult(success=True, drawingml=drawingml, fallback=fallback, metadata=metadata)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _parse_parameters(self, primitive: etree._Element) -> ColorMatrixParams:
        matrix_type = (primitive.get("type") or "matrix").strip()
        values_attr = primitive.get("values") or ""
        if matrix_type in {"matrix", "saturate", "hueRotate"} and values_attr:
            values = self._parse_floats(values_attr)
        else:
            values = []
        return ColorMatrixParams(matrix_type=matrix_type, values=values)

    def _parse_floats(self, payload: str) -> List[float]:
        cleaned = payload.replace(",", " ").split()
        values: List[float] = []
        for token in cleaned:
            try:
                values.append(float(token))
            except ValueError:
                continue
        return values

    def _to_drawingml(self, params: ColorMatrixParams) -> str:
        if params.matrix_type == "saturate":
            value = params.values[0] if params.values else 1.0
            sat = max(0, min(int(value * 100000), 200000))

            effectLst = a_elem("effectLst")
            clrChange = a_sub(effectLst, "clrChange")
            clrTo = a_sub(clrChange, "clrTo")
            srgbClr = a_sub(clrTo, "srgbClr", val="FFFFFF")
            a_sub(srgbClr, "satMod", val=sat)
            return to_string(effectLst)

        if params.matrix_type == "hueRotate":
            degrees = params.values[0] if params.values else 0.0
            hue = int((degrees % 360) * 60000)

            effectLst = a_elem("effectLst")
            hsl = a_sub(effectLst, "hsl")
            a_sub(hsl, "hue", val=hue)
            return to_string(effectLst)

        if params.matrix_type == "luminanceToAlpha":
            effectLst = a_elem("effectLst")
            a_sub(effectLst, "alpha", val="50000")
            return to_string(effectLst)

        if params.matrix_type == "matrix":
            flattened = " ".join(f"{value:.6g}" for value in params.values[:20])
            # Note: XML comments not directly supported in element building
            # This uses extLst for custom matrix values
            extLst = a_elem("extLst")
            ext = a_sub(extLst, "ext", uri="{FEColorMatrix}")
            a_sub(ext, "prop", val=flattened)
            return to_string(extLst)

        # Unsupported type - return empty comment placeholder
        return ""


__all__ = ["ColorMatrixFilter"]
