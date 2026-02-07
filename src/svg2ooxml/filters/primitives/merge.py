"""feMerge filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult


@dataclass
class MergeParams:
    inputs: list[str]


class MergeFilter(Filter):
    primitive_tags = ("feMerge",)
    filter_type = "merge"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = self._parse_params(primitive)
        pipeline = context.pipeline_state or {}
        resolved: list[tuple[str, FilterResult]] = []
        missing: list[str] = []
        for name in params.inputs:
            if name in {"SourceGraphic", "SourceAlpha"}:
                missing.append(name)
                continue
            candidate = pipeline.get(name)
            if candidate is None:
                missing.append(name)
            else:
                resolved.append((name, candidate))

        metadata = {
            "filter_type": self.filter_type,
            "inputs": list(params.inputs),
        }
        if missing:
            metadata["missing_inputs"] = missing

        drawingml = self._combine(resolved, params.inputs)
        fallback = self._collect_fallback(resolved)
        if missing and not resolved:
            fallback = fallback or "bitmap"
        return FilterResult(
            success=True,
            drawingml=drawingml,
            fallback=fallback,
            metadata=metadata,
        )

    def _parse_params(self, primitive: etree._Element) -> MergeParams:
        inputs: list[str] = []
        for node in primitive:
            if not hasattr(node, "tag"):
                continue
            local = node.tag.split("}", 1)[-1] if "}" in node.tag else node.tag
            if local != "feMergeNode":
                continue
            ref = node.get("in") or "SourceGraphic"
            inputs.append(ref)
        return MergeParams(inputs=inputs)

    def _combine(self, inputs: list[tuple[str, FilterResult]], order: list[str]) -> str:
        if not inputs:
            return ""
        parts = []
        for name in order:
            for candidate_name, result in inputs:
                if candidate_name == name and result.drawingml:
                    parts.append(result.drawingml)
        return "".join(parts)

    def _collect_fallback(self, inputs: list[tuple[str, FilterResult]]) -> str | None:
        for _name, result in inputs:
            if result.fallback:
                return result.fallback
        return None


__all__ = ["MergeFilter"]
