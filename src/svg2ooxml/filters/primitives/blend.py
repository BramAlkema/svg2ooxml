"""feBlend filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.common.conversions.opacity import opacity_to_ppt

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string
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


@dataclass
class OverlayInfo:
    color: str
    opacity: float
    approximation: str | None = None


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
        policy = {}
        if isinstance(context.options, dict):
            policy = context.options.get("policy") or {}
        approximation_allowed = bool(policy.get("approximation_allowed", True))
        prefer_rasterization = bool(policy.get("prefer_rasterization", False))

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

            # Record telemetry
            if context.tracer:
                context.tracer.record_decision(
                    element_type="feBlend",
                    strategy="native" if drawingml else "emf",
                    reason=f"Normal blend mode: {'native merge' if drawingml else 'no drawable content'}",
                    metadata={"mode": "normal", "has_drawingml": bool(drawingml)},
                )

            return FilterResult(
                success=True,
                drawingml=drawingml,
                fallback=fallback,
                metadata=metadata,
                warnings=warnings,
            )

        if params.mode in {"multiply", "screen", "darken", "lighten"}:
            overlay_info = self._extract_overlay_color(top_result)
            if overlay_info and overlay_info.approximation and not approximation_allowed:
                overlay_info = None
            overlay = self._build_overlay(params.mode, base_result, overlay_info)
            if overlay:
                fallback = self._merge_fallback(base_result, top_result)
                warnings = self._collect_warnings(base_result, top_result)
                metadata["native_support"] = True
                if overlay_info and overlay_info.approximation:
                    metadata["overlay_approximation"] = overlay_info.approximation

                # Record telemetry for successful native blend
                if context.tracer:
                    context.tracer.record_decision(
                        element_type="feBlend",
                        strategy="native",
                        reason=f"Supported blend mode: {params.mode}",
                        metadata={"mode": params.mode, "blend_type": "fillOverlay"},
                    )

                return FilterResult(
                    success=True,
                    drawingml=overlay,
                    fallback=fallback,
                    metadata=metadata,
                    warnings=warnings,
                )

            metadata["native_support"] = False
            metadata["fallback_reason"] = "missing_overlay"
            fallback = "bitmap" if (approximation_allowed or prefer_rasterization) else "emf"
            metadata["approximation_allowed"] = approximation_allowed
            fallback_assets = self._collect_fallback_assets(base_result, top_result)
            if fallback_assets:
                metadata["fallback_assets"] = fallback_assets
            if context.tracer:
                context.tracer.record_decision(
                    element_type="feBlend",
                    strategy="raster" if fallback == "bitmap" else "emf",
                    reason=f"Blend overlay not representable; fallback={fallback}",
                    metadata={"mode": params.mode, "fallback": fallback},
                )
            return FilterResult(
                success=True,
                drawingml="",
                fallback=fallback,
                metadata=metadata,
                warnings=[f"feBlend mode '{params.mode}' rendered via {fallback} fallback"],
            )

        # Unsupported mode - fallback to EMF
        metadata["native_support"] = False
        metadata["fallback_reason"] = f"mode:{params.mode}"

        # Record telemetry for unsupported mode
        if context.tracer:
            context.tracer.record_decision(
                element_type="feBlend",
                strategy="emf",
                reason=f"Unsupported blend mode: {params.mode}",
                metadata={"mode": params.mode, "supported_modes": list(SUPPORTED_MODES)},
            )

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
        overlay_info: OverlayInfo | None,
    ) -> str | None:
        if overlay_info is None:
            return None

        base_fragment = (base.drawingml or "").strip() if base else ""
        overlay_child = self._overlay_child(mode, overlay_info)
        if overlay_child is None:
            return None
        return merge_effect_fragments(base_fragment, overlay_child)

    @staticmethod
    def _overlay_child(mode: str, color_info: OverlayInfo) -> str | None:
        blend_map = {
            "multiply": "mult",
            "screen": "screen",
            "darken": "darken",
            "lighten": "lighten",
        }
        blend = blend_map.get(mode)
        if blend is None:
            return None
        color = color_info.color
        opacity = color_info.opacity
        alpha = opacity_to_ppt(opacity)

        fillOverlay = a_elem("fillOverlay", blend=blend)
        solidFill = a_sub(fillOverlay, "solidFill")
        srgbClr = a_sub(solidFill, "srgbClr", val=color)
        a_sub(srgbClr, "alpha", val=alpha)

        return to_string(fillOverlay)

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

    @classmethod
    def _extract_overlay_color(cls, result: FilterResult | None) -> OverlayInfo | None:
        if result is None or not result.metadata:
            return None
        metadata = result.metadata
        if "flood_color" in metadata:
            color = str(metadata["flood_color"]).strip().lstrip("#").upper()
            if len(color) == 3:
                color = "".join(ch * 2 for ch in color)
            opacity = float(metadata.get("flood_opacity", 1.0))
            return OverlayInfo(color=color, opacity=opacity)

        fill_meta = metadata.get("fill")
        if isinstance(fill_meta, dict) and fill_meta.get("type") == "solid":
            color = str(fill_meta.get("rgb") or "")
            color = color.strip().lstrip("#").upper()
            if len(color) == 3:
                color = "".join(ch * 2 for ch in color)
            if len(color) != 6:
                return None
            opacity = float(fill_meta.get("opacity", metadata.get("opacity", 1.0)))
            return OverlayInfo(color=color, opacity=opacity)

        if isinstance(fill_meta, dict) and fill_meta.get("type") in {"linearGradient", "radialGradient"}:
            stops = fill_meta.get("stops")
            if isinstance(stops, list) and stops:
                approx = cls._approximate_gradient_color(stops)
                if approx is not None:
                    color, opacity = approx
                    return OverlayInfo(color=color, opacity=opacity, approximation="gradient_avg")

        if isinstance(fill_meta, dict) and fill_meta.get("type") == "pattern":
            color = fill_meta.get("foreground") or fill_meta.get("background")
            if isinstance(color, str) and color:
                token = color.strip().lstrip("#").upper()
                if len(token) == 3:
                    token = "".join(ch * 2 for ch in token)
                if len(token) == 6:
                    opacity = float(metadata.get("opacity", 1.0))
                    return OverlayInfo(color=token, opacity=opacity, approximation="pattern_color")

        return None

    @staticmethod
    def _approximate_gradient_color(stops: list[dict[str, object]]) -> tuple[str, float] | None:
        parsed: list[tuple[float, int, int, int, float]] = []
        total = len(stops)
        for index, stop in enumerate(stops):
            if not isinstance(stop, dict):
                continue
            rgb = stop.get("rgb")
            if not isinstance(rgb, str):
                continue
            token = rgb.strip().lstrip("#").upper()
            if len(token) == 3:
                token = "".join(ch * 2 for ch in token)
            if len(token) != 6:
                continue
            try:
                r = int(token[0:2], 16)
                g = int(token[2:4], 16)
                b = int(token[4:6], 16)
            except ValueError:
                continue
            try:
                offset = float(stop.get("offset", index / max(1, total - 1)))
            except (TypeError, ValueError):
                offset = index / max(1, total - 1)
            offset = max(0.0, min(1.0, offset))
            try:
                opacity = float(stop.get("opacity", 1.0))
            except (TypeError, ValueError):
                opacity = 1.0
            opacity = max(0.0, min(1.0, opacity))
            parsed.append((offset, r, g, b, opacity))

        if not parsed:
            return None
        parsed.sort(key=lambda item: item[0])
        if parsed[0][0] > 0.0:
            parsed.insert(0, (0.0, parsed[0][1], parsed[0][2], parsed[0][3], parsed[0][4]))
        if parsed[-1][0] < 1.0:
            parsed.append((1.0, parsed[-1][1], parsed[-1][2], parsed[-1][3], parsed[-1][4]))

        total_weight = 0.0
        sum_r = sum_g = sum_b = 0.0
        sum_opacity = 0.0
        for idx in range(len(parsed) - 1):
            o0, r0, g0, b0, a0 = parsed[idx]
            o1, r1, g1, b1, a1 = parsed[idx + 1]
            weight = max(0.0, o1 - o0)
            if weight <= 0:
                continue
            avg_r = (r0 + r1) / 2.0
            avg_g = (g0 + g1) / 2.0
            avg_b = (b0 + b1) / 2.0
            avg_a = (a0 + a1) / 2.0
            sum_r += avg_r * weight
            sum_g += avg_g * weight
            sum_b += avg_b * weight
            sum_opacity += avg_a * weight
            total_weight += weight

        if total_weight <= 0:
            return None
        r = int(round(sum_r / total_weight))
        g = int(round(sum_g / total_weight))
        b = int(round(sum_b / total_weight))
        avg_opacity = max(0.0, min(1.0, sum_opacity / total_weight))
        return f"{r:02X}{g:02X}{b:02X}", avg_opacity

    @staticmethod
    def _collect_fallback_assets(*results: FilterResult | None) -> list[dict[str, object]]:
        assets: list[dict[str, object]] = []
        for result in results:
            if result is None or not isinstance(result.metadata, dict):
                continue
            candidate = result.metadata.get("fallback_assets")
            if isinstance(candidate, list):
                for item in candidate:
                    if isinstance(item, dict):
                        assets.append(dict(item))
        return assets


__all__ = ["BlendFilter"]
