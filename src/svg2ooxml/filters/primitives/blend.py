"""feBlend filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils import build_exporter_hook


SUPPORTED_MODES = {
    "normal",
    "multiply",
    "screen",
    "darken",
    "lighten",
}


@dataclass
class BlendParams:
    mode: str
    input_1: str | None
    input_2: str | None
    result: str | None


class BlendFilter(Filter):
    primitive_tags = ("feBlend",)
    filter_type = "blend"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = self._parse_params(primitive)
        pipeline = context.pipeline_state or {}
        inputs = self._resolve_inputs(pipeline, params)
        metadata = {
            "filter_type": self.filter_type,
            "mode": params.mode,
            "input_1": params.input_1,
            "input_2": params.input_2,
            "result": params.result,
        }
        if inputs:
            metadata["inputs"] = [name for name, _ in inputs]
            metadata["native_support"] = False
            metadata["fallback_reason"] = f"mode:{params.mode}"
            drawingml = ""
            fallback = "emf"
            return FilterResult(
                success=True,
                drawingml=drawingml,
                fallback=fallback,
                metadata=metadata,
                warnings=[f"feBlend mode '{params.mode}' rendered via EMF fallback"],
            )

        metadata["native_support"] = False
        metadata["fallback_reason"] = f"mode:{params.mode}"
        metadata["inputs"] = metadata.get("inputs") or []
        return FilterResult(
            success=True,
            drawingml="",
            fallback="emf",
            metadata=metadata,
            warnings=[f"feBlend mode '{params.mode}' rendered via EMF fallback"],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_params(self, primitive: etree._Element) -> BlendParams:
        mode = (primitive.get("mode") or "normal").strip().lower()
        if mode not in SUPPORTED_MODES:
            mode = "normal"
        input_1 = primitive.get("in")
        input_2 = primitive.get("in2")
        result = primitive.get("result")
        return BlendParams(mode=mode, input_1=input_1, input_2=input_2, result=result)

    def _resolve_inputs(
        self,
        pipeline: dict[str, FilterResult],
        params: BlendParams,
    ) -> list[tuple[str, FilterResult]]:
        resolved: list[tuple[str, FilterResult]] = []
        for name in (params.input_1, params.input_2):
            if not name or name in {"SourceGraphic", "SourceAlpha"}:
                continue
            candidate = pipeline.get(name)
            if candidate is not None:
                resolved.append((name, candidate))
        return resolved

    def _placeholder_drawingml(self, params: BlendParams) -> str:
        return build_exporter_hook(
            "blend",
            {
                "mode": params.mode,
                "status": "fallback",
            },
        )


__all__ = ["BlendFilter"]
