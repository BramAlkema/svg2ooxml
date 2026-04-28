"""Native `over` operator handling for feComposite."""

from __future__ import annotations

from svg2ooxml.filters.base import FilterResult
from svg2ooxml.filters.utils.dml import (
    is_effect_container,
    merge_effect_fragments,
)


class CompositeOverMixin:
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
            fragment = parts[0]
            if not is_effect_container(fragment):
                fragment = f"<a:effectLst>{fragment}</a:effectLst>"
            return fragment, fallback, tuple(warnings)

        merged = merge_effect_fragments(*parts)
        if merged:
            return merged, fallback, tuple(warnings)
        return "".join(parts), fallback, tuple(warnings)


__all__ = ["CompositeOverMixin"]
