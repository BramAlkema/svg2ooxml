"""Mask promotion and alpha-composition helpers for feComposite."""

from __future__ import annotations

from svg2ooxml.common.conversions.opacity import opacity_to_ppt, parse_opacity
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, graft_xml_fragment, to_string
from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.primitives.composite_types import CompositeParams
from svg2ooxml.filters.primitives.result_utils import approximate_gradient_color
from svg2ooxml.filters.utils.dml import (
    extract_effect_children,
    is_effect_container,
    merge_effect_fragments,
)


class CompositeMaskingMixin:
    def _is_simple_mask(
        self,
        params: CompositeParams,
        input_1: FilterResult | None,
        input_2: FilterResult | None,
        context: FilterContext,
    ) -> bool:
        """Detect whether a mask can be promoted to native DrawingML."""
        if params.operator not in {"in", "out", "atop", "xor"}:
            return False
        if params.operator == "arithmetic":
            return False

        input_2_name = params.input_2 or "SourceAlpha"
        if input_2_name == "SourceAlpha":
            return True

        if input_2 is None:
            return False

        if not input_2.metadata.get("native_support", True):
            return False

        mask_fragment = (input_2.drawingml or "").strip()
        if not mask_fragment:
            return False

        return mask_fragment.startswith("<a:effectLst")

    def _combine_masking(
        self,
        operator: str,
        source: FilterResult | None,
        mask: FilterResult | None,
        *,
        allow_approximation: bool,
        enable_effect_dag: bool,
    ) -> tuple[str, str | None, str | None]:
        if mask is None:
            return "", "missing_mask", None
        if isinstance(mask.metadata, dict) and mask.metadata.get("native_support") is False:
            return "", "mask_missing_effects", None

        source_fragment = (source.drawingml or "").strip() if source else ""
        mask_fragment = (mask.drawingml or "").strip()
        if not mask_fragment:
            fallback_fragment, approximation = self._mask_effect_from_metadata(mask, allow_approximation)
            if fallback_fragment:
                mask_fragment = fallback_fragment
            else:
                return "", "mask_empty", None
        else:
            approximation = None

        if not is_effect_container(mask_fragment):
            wrapped = ""
            if mask_fragment.lstrip().startswith("<a:"):
                wrapped = merge_effect_fragments(mask_fragment)
            if wrapped:
                mask_fragment = wrapped
            else:
                fallback_fragment, approximation = self._mask_effect_from_metadata(mask, allow_approximation)
                if fallback_fragment:
                    mask_fragment = fallback_fragment
                else:
                    return "", "mask_missing_effects", None
        mask_children = extract_effect_children(mask_fragment)
        if not mask_children:
            return "", "mask_missing_effects", None

        alpha_tag = self._alpha_tag_for_operator(operator)
        outer_container = a_elem("effectDag" if enable_effect_dag else "effectLst")
        if enable_effect_dag:
            a_sub(outer_container, "cont")

        if source_fragment:
            source_children = (
                extract_effect_children(source_fragment)
                if is_effect_container(source_fragment)
                else source_fragment
            )
            if source_children:
                try:
                    graft_xml_fragment(outer_container, source_children)
                except Exception:
                    pass

        alpha_elem = a_sub(outer_container, alpha_tag)
        a_sub(alpha_elem, "cont")
        inner_effect_lst = a_sub(alpha_elem, "effectLst")

        try:
            graft_xml_fragment(inner_effect_lst, mask_children)
        except Exception:
            pass

        return to_string(outer_container), None, approximation

    def _mask_effect_from_metadata(
        self,
        mask: FilterResult,
        allow_approximation: bool,
    ) -> tuple[str | None, str | None]:
        if not isinstance(mask.metadata, dict):
            return None, None
        if not allow_approximation:
            return None, None
        color = None
        opacity = 1.0
        if "flood_color" in mask.metadata:
            color = str(mask.metadata.get("flood_color") or "").strip().lstrip("#").upper()
            opacity = parse_opacity(mask.metadata.get("flood_opacity"), 1.0)
        else:
            fill_meta = mask.metadata.get("fill")
            if isinstance(fill_meta, dict) and fill_meta.get("type") == "solid":
                color = str(fill_meta.get("rgb") or "").strip().lstrip("#").upper()
                opacity = parse_opacity(fill_meta.get("opacity", mask.metadata.get("opacity")), 1.0)
            elif isinstance(fill_meta, dict) and fill_meta.get("type") in {"linearGradient", "radialGradient"}:
                stops = fill_meta.get("stops")
                if isinstance(stops, list) and stops:
                    approx = self._approximate_gradient_color(stops)
                    if approx is not None:
                        color, opacity = approx
                        return self._solid_mask_fragment(color, opacity), "gradient_mask_avg"
            elif isinstance(fill_meta, dict) and fill_meta.get("type") == "pattern":
                candidate = fill_meta.get("foreground") or fill_meta.get("background")
                if isinstance(candidate, str) and candidate:
                    color = candidate.strip().lstrip("#").upper()
                    opacity = parse_opacity(mask.metadata.get("opacity"), 1.0)
        if not color:
            return None, None
        if len(color) == 3:
            color = "".join(ch * 2 for ch in color)
        if len(color) != 6:
            return None, None
        return self._solid_mask_fragment(color, opacity), "solid_mask"

    @staticmethod
    def _solid_mask_fragment(color: str, opacity: float) -> str:
        alpha = opacity_to_ppt(max(0.0, min(opacity, 1.0)))
        effect_lst = a_elem("effectLst")
        solid_fill = a_sub(effect_lst, "solidFill")
        srgb_clr = a_sub(solid_fill, "srgbClr", val=color)
        a_sub(srgb_clr, "alpha", val=alpha)
        return to_string(effect_lst)

    @staticmethod
    def _approximate_gradient_color(stops: list[dict[str, object]]) -> tuple[str, float] | None:
        return approximate_gradient_color(stops)

    @staticmethod
    def _alpha_tag_for_operator(operator: str) -> str:
        mapping = {
            "in": "alphaModFix",
            "out": "alphaMod",
            "atop": "alphaModFix",
            "xor": "alphaMod",
        }
        return mapping.get(operator, "alphaModFix")


__all__ = ["CompositeMaskingMixin"]
