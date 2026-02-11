"""Color matrix filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
from svg2ooxml.filters.base import Filter, FilterContext, FilterResult


@dataclass
class ColorMatrixParams:
    matrix_type: str
    values: list[float]


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
            if not values_list or self._is_identity_matrix(values_list):
                metadata["native_support"] = True
                metadata["no_op"] = True
                metadata["reason"] = "identity_matrix"
                return FilterResult(
                    success=True,
                    drawingml="",
                    fallback=None,
                    metadata=metadata,
                )
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

    def _parse_floats(self, payload: str) -> list[float]:
        cleaned = payload.replace(",", " ").split()
        values: list[float] = []
        for token in cleaned:
            try:
                values.append(float(token))
            except ValueError:
                continue
        return values

    def _to_drawingml(self, params: ColorMatrixParams) -> str:
        if params.matrix_type == "saturate":
            # <a:clrChange> is valid in CT_Blip, not CT_EffectList.
            # No valid effectLst equivalent for feColorMatrix(saturate).
            return ""

        if params.matrix_type == "hueRotate":
            # No valid OOXML equivalent in effectLst — <a:hsl> is a color
            # transform, not an effect.  Return empty to avoid schema violation.
            return ""

        if params.matrix_type == "luminanceToAlpha":
            # <a:alpha> is a color transform, not a valid effectLst child.
            # No direct OOXML equivalent for luminanceToAlpha in effectLst.
            return ""

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

    @staticmethod
    def _is_identity_matrix(values: list[float]) -> bool:
        if len(values) != 20:
            return False
        identity = [
            1.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 1.0, 0.0,
        ]
        tol = 1e-6
        return all(abs(a - b) <= tol for a, b in zip(values, identity, strict=True))


__all__ = ["ColorMatrixFilter"]
