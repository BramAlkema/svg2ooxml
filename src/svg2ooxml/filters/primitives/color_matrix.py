"""Color matrix filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.common.conversions.angles import degrees_to_ppt
from svg2ooxml.common.conversions.scale import scale_to_ppt
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
from svg2ooxml.filters.base import (
    Filter,
    FilterContext,
    FilterResult,
    stitch_blip_transforms,
)
from svg2ooxml.filters.planner_common import is_identity_color_matrix
from svg2ooxml.filters.utils import parse_float_list


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
        policy = context.policy
        approximation_allowed = bool(policy.get("approximation_allowed", True))
        prefer_rasterization = bool(policy.get("prefer_rasterization", False))
        enable_native_color_transforms = bool(policy.get("enable_native_color_transforms", False))
        metadata = {
            "filter_type": self.filter_type,
            "matrix_type": params.matrix_type,
            "value_count": len(params.values),
            "matrix_source": raw_values,
        }
        if params.values:
            metadata["values"] = list(params.values)
            metadata["value_count"] = len(params.values)
        if params.matrix_type == "matrix":
            values_list = list(params.values)
            if not values_list and raw_values:
                values_list = parse_float_list(raw_values)
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
        if params.matrix_type in {"saturate", "hueRotate", "luminanceToAlpha"}:
            if params.matrix_type == "saturate":
                value = params.values[0] if params.values else 1.0
                if abs(value - 1.0) <= 1e-6:
                    metadata["native_support"] = True
                    metadata["no_op"] = True
                    metadata["reason"] = "identity_saturate"
                    return FilterResult(
                        success=True,
                        drawingml="",
                        fallback=None,
                        metadata=metadata,
                    )
            if params.matrix_type == "hueRotate":
                value = params.values[0] if params.values else 0.0
                if abs(value) <= 1e-6:
                    metadata["native_support"] = True
                    metadata["no_op"] = True
                    metadata["reason"] = "identity_huerotate"
                    return FilterResult(
                        success=True,
                        drawingml="",
                        fallback=None,
                        metadata=metadata,
                    )
            if enable_native_color_transforms:
                stitch_blip_transforms(metadata, self._blip_transform_candidates(params))
            metadata["native_support"] = False
            metadata["fallback_reason"] = f"{params.matrix_type}_requires_raster"
            metadata["approximation_allowed"] = approximation_allowed
            metadata["prefer_rasterization"] = prefer_rasterization
            fallback = "bitmap" if (approximation_allowed or prefer_rasterization) else "emf"
            return FilterResult(
                success=True,
                drawingml="",
                fallback=fallback,
                metadata=metadata,
                warnings=[f"feColorMatrix({params.matrix_type}) rendered via {fallback} fallback"],
            )
        return FilterResult(success=True, drawingml=drawingml, fallback=fallback, metadata=metadata)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _parse_parameters(self, primitive: etree._Element) -> ColorMatrixParams:
        matrix_type = (primitive.get("type") or "matrix").strip()
        values_attr = primitive.get("values") or ""
        if matrix_type in {"matrix", "saturate", "hueRotate"} and values_attr:
            values = parse_float_list(values_attr)
        else:
            values = []
        return ColorMatrixParams(matrix_type=matrix_type, values=values)

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
        return is_identity_color_matrix(values)

    @staticmethod
    def _blip_transform_candidates(params: ColorMatrixParams) -> list[dict[str, object]]:
        if params.matrix_type == "saturate":
            value = params.values[0] if params.values else 1.0
            amount = max(0, min(scale_to_ppt(value), 400000))
            return [{"tag": "satMod", "val": amount}]

        if params.matrix_type == "hueRotate":
            value = params.values[0] if params.values else 0.0
            angle = degrees_to_ppt(value)
            if angle == 0:
                return []
            return [{"tag": "hueOff", "val": angle}]

        return []


__all__ = ["ColorMatrixFilter"]
