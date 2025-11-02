"""feComposite filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult


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
        inputs = self._resolve_inputs(pipeline, params)
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

        metadata["inputs"] = [name for name, _ in inputs]
        if inputs:
            metadata["source_metadata"] = {
                name: dict(candidate.metadata or {})
                for name, candidate in inputs
                if candidate.metadata
            }

        if params.operator == "over":
            drawingml, fallback, propagated_warnings = self._combine_over(inputs)
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
        if params.operator in {"in", "out", "atop", "xor"} and len(inputs) == 2:
            drawingml, fallback = self._combine_masking(params.operator, inputs)
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

        if inputs:
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

    def _resolve_inputs(
        self,
        pipeline: dict[str, FilterResult],
        params: CompositeParams,
    ) -> list[tuple[str, FilterResult]]:
        resolved: list[tuple[str, FilterResult]] = []
        for name in (params.input_1, params.input_2):
            if not name or name in {"SourceGraphic", "SourceAlpha"}:
                continue
            candidate = pipeline.get(name)
            if candidate is not None:
                resolved.append((name, candidate))
        return resolved

    def _combine_over(
        self,
        inputs: list[tuple[str, FilterResult]],
    ) -> tuple[str, str | None, tuple[str, ...]]:
        if not inputs:
            return "", None, ()

        parts: list[str] = []
        fallback: str | None = None
        warnings: list[str] = []
        for name, result in inputs:
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

        if all(self._looks_like_effect_list(part) for part in parts):
            inner = "".join(self._extract_effect_children(part) for part in parts)
            return f"<a:effectLst>{inner}</a:effectLst>", fallback, tuple(warnings)

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

    @staticmethod
    def _looks_like_effect_list(drawingml: str) -> bool:
        return drawingml.startswith("<a:effectLst")

    @staticmethod
    def _extract_effect_children(drawingml: str) -> str:
        if drawingml.endswith("/>"):
            return ""
        start = drawingml.find(">")
        end = drawingml.rfind("</a:effectLst>")
        if start == -1 or end == -1 or end <= start:
            return drawingml
        return drawingml[start + 1 : end]

    def _combine_masking(
        self,
        operator: str,
        inputs: list[tuple[str, FilterResult]],
    ) -> tuple[str, str | None]:
        source_graphic = None
        mask_input = None
        for name, result in inputs:
            if name == "SourceGraphic":
                source_graphic = result
            else:
                mask_input = result

        if mask_input is None:
            return "", "missing_mask"

        source_fragment = (source_graphic.drawingml or "").strip() if source_graphic else ""
        mask_fragment = (mask_input.drawingml or "").strip()
        if not mask_fragment:
            return "", "mask_empty"

        mask_children = self._extract_effect_children(mask_fragment) if self._looks_like_effect_list(mask_fragment) else ""
        if not mask_children:
            return "", "mask_missing_effects"

        alpha_tag = self._alpha_tag_for_operator(operator)
        base_fragments = []
        if source_fragment:
            if self._looks_like_effect_list(source_fragment):
                base_fragments.append(self._extract_effect_children(source_fragment))
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
