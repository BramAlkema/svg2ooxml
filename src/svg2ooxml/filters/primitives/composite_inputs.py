"""Input parsing and shared scalar helpers for feComposite."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.filters.base import FilterResult
from svg2ooxml.filters.metadata import FilterFallbackAssetPayload
from svg2ooxml.filters.primitives.composite_types import (
    SUPPORTED_OPERATORS,
    CompositeParams,
)
from svg2ooxml.filters.primitives.result_utils import (
    collect_fallback_assets,
    merge_fallback_mode,
)


def lookup_filter_input(
    pipeline: dict[str, FilterResult],
    name: str | None,
) -> FilterResult | None:
    """Resolve a named primitive input from the active filter pipeline."""

    if not name:
        return None
    candidate = pipeline.get(name)
    if candidate is not None:
        return candidate
    if name in {"SourceGraphic", "SourceAlpha"}:
        return pipeline.get(name)
    return None


class CompositeInputMixin:
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
        return lookup_filter_input(pipeline, name)

    def _arithmetic_passthrough(self, params: CompositeParams) -> str | None:
        if params.operator != "arithmetic":
            return None
        tol = 1e-6
        if abs(params.k1) > tol or abs(params.k4) > tol:
            return None
        if abs(params.k2 - 1.0) <= tol and abs(params.k3) <= tol:
            return "in"
        if abs(params.k2) <= tol and abs(params.k3 - 1.0) <= tol:
            return "in2"
        return None

    @staticmethod
    def _merge_fallback(current: str | None, new_value: str | None) -> str | None:
        return merge_fallback_mode(current, new_value)

    @staticmethod
    def _collect_fallback_assets(
        *results: FilterResult | None,
    ) -> list[FilterFallbackAssetPayload]:
        return collect_fallback_assets(*results)


__all__ = ["CompositeInputMixin", "lookup_filter_input"]
