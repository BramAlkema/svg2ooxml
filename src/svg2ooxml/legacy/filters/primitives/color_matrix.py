"""Color matrix filter primitive."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult


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
            return f'<a:effectLst><a:clrChange><a:clrTo><a:srgbClr val="FFFFFF"><a:satMod val="{sat}"/></a:srgbClr></a:clrTo></a:clrChange></a:effectLst>'
        if params.matrix_type == "hueRotate":
            degrees = params.values[0] if params.values else 0.0
            hue = int((degrees % 360) * 60000)
            return f'<a:effectLst><a:hsl><a:hue val="{hue}"/></a:hsl></a:effectLst>'
        if params.matrix_type == "luminanceToAlpha":
            return '<a:effectLst><a:alpha val="50000"/></a:effectLst>'
        if params.matrix_type == "matrix":
            flattened = " ".join(f"{value:.6g}" for value in params.values[:20])
            return f'<!-- feColorMatrix matrix -->\n<a:extLst><a:ext uri="{{FEColorMatrix}}"><a:prop val="{flattened}"/></a:ext></a:extLst>'
        return "<!-- Unsupported feColorMatrix type -->"


__all__ = ["ColorMatrixFilter"]
