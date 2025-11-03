"""feBlend filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils.dml import merge_effect_fragments


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
        base_name = params.input_1 or "SourceGraphic"
        top_name = params.input_2 or "SourceGraphic"
        base_result = self._lookup_input(pipeline, base_name)
        top_result = self._lookup_input(pipeline, top_name)

        metadata = {
            "filter_type": self.filter_type,
            "mode": params.mode,
            "input_1": params.input_1,
            "input_2": params.input_2,
            "result": params.result,
        }
        metadata["inputs"] = [name for name in (base_name, top_name) if name]

        if params.mode == "normal":
            drawingml, fallback, warnings = self._combine_normal(base_result, top_result)
            metadata["native_support"] = bool(drawingml)
            if fallback:
                metadata["fallback_reason"] = fallback
            return FilterResult(
                success=True,
                drawingml=drawingml,
                fallback=fallback,
                metadata=metadata,
                warnings=warnings,
            )

        if params.mode in {"multiply", "screen", "darken", "lighten"}:
            overlay = self._build_overlay(params.mode, base_result, top_result)
            if overlay:
                fallback = self._merge_fallback(base_result, top_result)
                warnings = self._collect_warnings(base_result, top_result)
                metadata["native_support"] = True
                return FilterResult(
                    success=True,
                    drawingml=overlay,
                    fallback=fallback,
                    metadata=metadata,
                    warnings=warnings,
                )

        metadata["native_support"] = False
        metadata["fallback_reason"] = f"mode:{params.mode}"
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

    def _combine_normal(
        self,
        base: FilterResult | None,
        top: FilterResult | None,
    ) -> tuple[str, str | None, tuple[str, ...]]:
        fragments: list[str] = []
        fallback: str | None = None
        warnings = self._collect_warnings(base, top)
        for result in (base, top):
            if result is None:
                continue
            fragment = (result.drawingml or "").strip()
            if fragment:
                fragments.append(fragment)
            fallback = self._merge_one_fallback(fallback, result.fallback)
        if not fragments:
            return "", fallback, warnings
        merged = merge_effect_fragments(*fragments)
        if merged:
            return merged, fallback, warnings
        return "".join(fragments), fallback, warnings

    def _build_overlay(
        self,
        mode: str,
        base: FilterResult | None,
        top: FilterResult | None,
    ) -> str | None:
        color_info = self._extract_overlay_color(top)
        if color_info is None:
            return None

        base_fragment = (base.drawingml or "").strip() if base else ""
        overlay_child = self._overlay_child(mode, color_info)
        if overlay_child is None:
            return None
        return merge_effect_fragments(base_fragment, overlay_child)

    @staticmethod
    def _overlay_child(mode: str, color_info: tuple[str, float]) -> str | None:
        blend_map = {
            "multiply": "mult",
            "screen": "screen",
            "darken": "darken",
            "lighten": "lighten",
        }
        blend = blend_map.get(mode)
        if blend is None:
            return None
        color, opacity = color_info
        alpha = int(round(max(0.0, min(opacity, 1.0)) * 100000))
        return (
            f'<a:fillOverlay blend="{blend}">'
            f'<a:solidFill><a:srgbClr val="{color}"><a:alpha val="{alpha}"/></a:srgbClr></a:solidFill>'
            "</a:fillOverlay>"
        )

    @staticmethod
    def _collect_warnings(*results: FilterResult | None) -> tuple[str, ...]:
        warnings: list[str] = []
        for result in results:
            if result is not None and result.warnings:
                warnings.extend(list(result.warnings))
        return tuple(warnings)

    @staticmethod
    def _merge_one_fallback(current: str | None, new_value: str | None) -> str | None:
        if new_value is None:
            return current
        if current is None:
            return new_value
        precedence = {"bitmap": 3, "raster": 3, "emf": 2, "vector": 1}
        current_rank = precedence.get(current, 0)
        new_rank = precedence.get(new_value, 0)
        return new_value if new_rank > current_rank else current

    def _merge_fallback(self, base: FilterResult | None, top: FilterResult | None) -> str | None:
        fallback: str | None = None
        for result in (base, top):
            if result is not None:
                fallback = self._merge_one_fallback(fallback, result.fallback)
        return fallback

    @staticmethod
    def _extract_overlay_color(result: FilterResult | None) -> tuple[str, float] | None:
        if result is None or not result.metadata:
            return None
        metadata = result.metadata
        if "flood_color" in metadata:
            color = str(metadata["flood_color"]).strip().lstrip("#").upper()
            if len(color) == 3:
                color = "".join(ch * 2 for ch in color)
            opacity = float(metadata.get("flood_opacity", 1.0))
            return color, opacity

        fill_meta = metadata.get("fill")
        if isinstance(fill_meta, dict) and fill_meta.get("type") == "solid":
            color = str(fill_meta.get("rgb") or "")
            color = color.strip().lstrip("#").upper()
            if len(color) == 3:
                color = "".join(ch * 2 for ch in color)
            if len(color) != 6:
                return None
            opacity = float(fill_meta.get("opacity", metadata.get("opacity", 1.0)))
            return color, opacity

        return None


__all__ = ["BlendFilter"]
