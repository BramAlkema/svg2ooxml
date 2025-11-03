"""feComposite filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils.dml import extract_effect_children, is_effect_list, merge_effect_fragments


SUPPORTED_OPERATORS = {
    "over",
    "in",
    "out",
    "atop",
    "xor",
    "arithmetic",
}


@dataclass
class CompositeParams:
    operator: str
    input_1: str | None
    input_2: str | None
    k1: float
    k2: float
    k3: float
    k4: float
    result: str | None


class CompositeFilter(Filter):
    primitive_tags = ("feComposite",)
    filter_type = "composite"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = self._parse_params(primitive)
        pipeline = context.pipeline_state or {}
        input_1_name = params.input_1 or "SourceGraphic"
        input_2_name = params.input_2 or ("SourceAlpha" if params.operator in {"in", "out"} else "SourceGraphic")

        input_1 = self._lookup_input(pipeline, input_1_name)
        input_2 = self._lookup_input(pipeline, input_2_name)

        metadata = {
            "filter_type": self.filter_type,
            "operator": params.operator,
            "input_1": params.input_1,
            "input_2": params.input_2,
            "result": params.result,
        }
        if params.operator == "arithmetic":
            metadata.update(
                {
                    "k1": params.k1,
                    "k2": params.k2,
                    "k3": params.k3,
                    "k4": params.k4,
                }
            )

        metadata["inputs"] = [name for name in (input_1_name, input_2_name) if name]
        source_metadata: dict[str, dict[str, object]] = {}
        if input_1 is not None and input_1.metadata:
            source_metadata[input_1_name] = dict(input_1.metadata)
        if input_2 is not None and input_2.metadata and input_2_name != input_1_name:
            source_metadata[input_2_name] = dict(input_2.metadata)
        if source_metadata:
            metadata["source_metadata"] = {
                key: value for key, value in source_metadata.items()
            }

        if params.operator == "over":
            drawingml, fallback, propagated_warnings = self._combine_over(input_1, input_2)
            metadata["native_support"] = bool(drawingml) or fallback is None
            if fallback:
                metadata["fallback_reason"] = f"from_inputs:{fallback}"
            return FilterResult(
                success=True,
                drawingml=drawingml,
                fallback=fallback,
                metadata=metadata,
                warnings=propagated_warnings,
            )
        if params.operator in {"in", "out", "atop", "xor"}:
            drawingml, fallback = self._combine_masking(params.operator, input_1, input_2)
            metadata["native_support"] = drawingml != ""
            if fallback:
                metadata["fallback_reason"] = fallback
            return FilterResult(
                success=True,
                drawingml=drawingml,
                fallback=None if drawingml else "emf",
                metadata=metadata,
                warnings=(),
            )

        if input_1 is not None or input_2 is not None:
            metadata["native_support"] = False
            metadata["fallback_reason"] = f"operator:{params.operator}"
            return FilterResult(
                success=True,
                drawingml="",
                fallback="emf",
                metadata=metadata,
                warnings=["feComposite requires vector fallback; EMF placeholder scheduled"],
            )

        metadata["native_support"] = False
        metadata["fallback_reason"] = f"operator:{params.operator}"
        return FilterResult(
            success=True,
            drawingml="",
            fallback="emf",
            metadata=metadata,
            warnings=["feComposite rendered via EMF fallback"],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_params(self, primitive: etree._Element) -> CompositeParams:
        operator = (primitive.get("operator") or "over").strip().lower()
        input_1 = primitive.get("in")
        input_2 = primitive.get("in2")
        result = primitive.get("result")
        k1 = self._parse_float(primitive.get("k1"))
        k2 = self._parse_float(primitive.get("k2"))
        k3 = self._parse_float(primitive.get("k3"))
        k4 = self._parse_float(primitive.get("k4"))
        if operator not in SUPPORTED_OPERATORS:
            operator = "over"
        return CompositeParams(
            operator=operator,
            input_1=input_1,
            input_2=input_2,
            k1=k1,
            k2=k2,
            k3=k3,
            k4=k4,
            result=result,
        )

    def _parse_float(self, token: str | None) -> float:
        if token is None:
            return 0.0
        try:
            return float(token)
        except ValueError:
            return 0.0

    def _lookup_input(
        self,
        pipeline: dict[str, FilterResult],
        name: str,
    ) -> FilterResult | None:
        if not name:
            return None
        candidate = pipeline.get(name)
        if candidate is not None:
            return candidate
        if name in {"SourceGraphic", "SourceAlpha"}:
            return pipeline.get(name)
        return None

    def _combine_over(
        self,
        input_1: FilterResult | None,
        input_2: FilterResult | None,
    ) -> tuple[str, str | None, tuple[str, ...]]:
        parts: list[str] = []
        fallback: str | None = None
        warnings: list[str] = []
        for result in (input_1, input_2):
            if result is None:
                continue
            snippet = (result.drawingml or "").strip()
            if snippet:
                parts.append(snippet)
            fallback = self._merge_fallback(fallback, result.fallback)
            if result.warnings:
                warnings.extend(list(result.warnings))

        if not parts:
            return "", fallback, tuple(warnings)

        if len(parts) == 1:
            return parts[0], fallback, tuple(warnings)

        merged = merge_effect_fragments(*parts)
        if merged:
            return merged, fallback, tuple(warnings)
        return "".join(parts), fallback, tuple(warnings)

    @staticmethod
    def _merge_fallback(current: str | None, new_value: str | None) -> str | None:
        if new_value is None:
            return current
        if current is None:
            return new_value
        precedence = {"bitmap": 3, "raster": 3, "emf": 2, "vector": 1}
        current_rank = precedence.get(current, 0)
        new_rank = precedence.get(new_value, 0)
        return new_value if new_rank > current_rank else current

    def _combine_masking(
        self,
        operator: str,
        source: FilterResult | None,
        mask: FilterResult | None,
    ) -> tuple[str, str | None]:
        if mask is None:
            return "", "missing_mask"

        source_fragment = (source.drawingml or "").strip() if source else ""
        mask_fragment = (mask.drawingml or "").strip()
        if not mask_fragment:
            return "", "mask_empty"

        mask_children = extract_effect_children(mask_fragment) if is_effect_list(mask_fragment) else ""
        if not mask_children:
            return "", "mask_missing_effects"

        alpha_tag = self._alpha_tag_for_operator(operator)
        base_fragments = []
        if source_fragment:
            if is_effect_list(source_fragment):
                base_fragments.append(extract_effect_children(source_fragment))
            else:
                base_fragments.append(source_fragment)
        alpha_fragment = (
            f"<a:{alpha_tag}><a:cont/><a:effectLst>{mask_children}</a:effectLst></a:{alpha_tag}>"
        )
        base_fragments.append(alpha_fragment)
        combined = "".join(base_fragments)
        return f"<a:effectLst>{combined}</a:effectLst>", None

    @staticmethod
    def _alpha_tag_for_operator(operator: str) -> str:
        mapping = {
            "in": "alphaModFix",
            "out": "alphaMod",
            "atop": "alphaModFix",
            "xor": "alphaMod",
        }
        return mapping.get(operator, "alphaModFix")


__all__ = ["CompositeFilter"]
