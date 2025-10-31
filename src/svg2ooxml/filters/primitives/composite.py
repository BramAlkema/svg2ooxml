"""feComposite filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import build_exporter_hook


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

        if inputs:
            metadata["inputs"] = [name for name, _ in inputs]
            metadata["native_support"] = False
            metadata["fallback_reason"] = f"operator:{params.operator}"
            drawingml = ""
            fallback = "emf"
            return FilterResult(
                success=True,
                drawingml=drawingml,
                fallback=fallback,
                metadata=metadata,
                warnings=["feComposite requires vector fallback; EMF placeholder scheduled"],
            )

        metadata["native_support"] = False
        metadata["fallback_reason"] = f"operator:{params.operator}"
        metadata["inputs"] = metadata.get("inputs") or []
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

    def _placeholder_drawingml(self, params: CompositeParams) -> str:
        return build_exporter_hook(
            "composite",
            {
                "operator": params.operator,
                "status": "fallback",
            },
        )


__all__ = ["CompositeFilter"]
