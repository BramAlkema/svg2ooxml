"""feComposite filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.color.utils import rgb_channels_to_hex
from svg2ooxml.common.conversions.opacity import opacity_to_ppt
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, graft_xml_fragment, to_string
from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils.dml import (
    extract_effect_children,
    is_effect_container,
    merge_effect_fragments,
)

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
        policy = context.policy
        approximation_allowed = bool(policy.get("approximation_allowed", True))
        prefer_rasterization = bool(policy.get("prefer_rasterization", False))
        enable_effect_dag = bool(policy.get("enable_effect_dag", False))

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

        if params.operator == "over" and input_1_name == "SourceGraphic":
            metadata["inputs"] = [name for name in (input_2_name,) if name]
        else:
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

            # Record telemetry for "over" operator
            if context.tracer:
                context.tracer.record_decision(
                    element_type="feComposite",
                    strategy="native" if drawingml else "emf",
                    reason=f"Over operator: {'native merge' if drawingml else f'fallback={fallback}'}",
                    metadata={"operator": "over", "has_drawingml": bool(drawingml)},
                )

            return FilterResult(
                success=True,
                drawingml=drawingml,
                fallback=fallback,
                metadata=metadata,
                warnings=propagated_warnings,
            )
        if params.operator in {"in", "out", "atop", "xor"}:
            # Check if this is a simple mask case that can be promoted
            is_simple = self._is_simple_mask(params, input_1, input_2, context)
            metadata["is_simple_mask"] = is_simple

            drawingml, fallback, approximation = self._combine_masking(
                params.operator,
                input_1,
                input_2,
                allow_approximation=approximation_allowed,
                enable_effect_dag=enable_effect_dag,
            )
            metadata["native_support"] = drawingml != ""
            if fallback:
                metadata["fallback_reason"] = fallback
            if approximation:
                metadata["mask_approximation"] = approximation

            # Record telemetry for masking operators
            tracer = getattr(context, "tracer", None)
            if tracer:
                if drawingml:
                    strategy = "native"
                elif fallback in {"mask_empty", "mask_missing_effects", "missing_mask"}:
                    strategy = "raster"
                else:
                    strategy = "emf"

                # Build reason string that clearly distinguishes success vs fallback
                if drawingml:
                    # Native success case
                    reason_parts = [f"Masking operator '{params.operator}'"]
                    if is_simple:
                        reason_parts.append("simple mask → alpha compositing")
                    else:
                        reason_parts.append("complex mask → alpha compositing")
                    reason = ": ".join(reason_parts)
                else:
                    # EMF fallback case
                    reason_parts = [f"Masking operator '{params.operator}'"]
                    if is_simple:
                        reason_parts.append(f"simple mask → fallback={fallback}")
                    else:
                        reason_parts.append(f"complex mask → fallback={fallback}")
                    reason = ": ".join(reason_parts)

                tracer.record_decision(
                    element_type="feComposite",
                    strategy=strategy,
                    reason=reason,
                    metadata={
                        "operator": params.operator,
                        "masking_type": strategy,
                        "is_simple_mask": is_simple,
                        "fallback_reason": fallback,
                    },
                )

            fallback_mode = None
            warnings: tuple[str, ...] = ()
            if not drawingml:
                if fallback in {"mask_empty", "mask_missing_effects", "missing_mask"}:
                    fallback_mode = "bitmap" if (approximation_allowed or prefer_rasterization) else "emf"
                    warnings = (f"feComposite mask fallback: {fallback}",)
                else:
                    fallback_mode = "emf"
            if fallback_mode:
                assets = self._collect_fallback_assets(input_1, input_2)
                if assets:
                    metadata["fallback_assets"] = assets
            return FilterResult(
                success=True,
                drawingml=drawingml,
                fallback=fallback_mode,
                metadata=metadata,
                warnings=warnings,
            )

        if params.operator == "arithmetic":
            passthrough = self._arithmetic_passthrough(params)
            if passthrough:
                source = input_1 if passthrough == "in" else input_2
                if source is not None:
                    metadata["native_support"] = True
                    metadata["pass_through"] = passthrough
                    metadata["no_op"] = True
                    drawingml = source.drawingml or ""

                    if context.tracer:
                        context.tracer.record_decision(
                            element_type="feComposite",
                            strategy="native",
                            reason=f"Arithmetic operator pass-through ({passthrough})",
                            metadata={
                                "operator": params.operator,
                                "pass_through": passthrough,
                            },
                        )

                    return FilterResult(
                        success=True,
                        drawingml=drawingml,
                        fallback=source.fallback,
                        metadata=metadata,
                        warnings=source.warnings,
                    )

        # Arithmetic or other unsupported operators
        if input_1 is not None or input_2 is not None:
            metadata["native_support"] = False
            metadata["fallback_reason"] = f"operator:{params.operator}"

            # Record telemetry for unsupported operator with inputs
            if context.tracer:
                context.tracer.record_decision(
                    element_type="feComposite",
                    strategy="emf",
                    reason=f"Unsupported operator: {params.operator}",
                    metadata={
                        "operator": params.operator,
                        "supported_operators": list(SUPPORTED_OPERATORS),
                        "has_inputs": True,
                    },
                )

            return FilterResult(
                success=True,
                drawingml="",
                fallback="emf",
                metadata=metadata,
                warnings=["feComposite requires vector fallback; EMF placeholder scheduled"],
            )

        metadata["native_support"] = False
        metadata["fallback_reason"] = f"operator:{params.operator}"

        # Record telemetry for unsupported operator without inputs
        if context.tracer:
            context.tracer.record_decision(
                element_type="feComposite",
                strategy="emf",
                reason=f"Unsupported operator without inputs: {params.operator}",
                metadata={"operator": params.operator, "has_inputs": False},
            )

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

    def _is_simple_mask(
        self,
        params: CompositeParams,
        input_1: FilterResult | None,
        input_2: FilterResult | None,
        context: FilterContext,
    ) -> bool:
        """Detect if this is a simple mask case that can be promoted to native DrawingML.

        Simple mask criteria:
        - Single input + SourceAlpha (most common masking pattern)
        - No arithmetic operator
        - Mask input has drawable content AND is natively supported
        - Mask DrawingML must be valid effect list structure
        - No complex filter chain (future: check context for chain complexity)
        """
        # Must be a masking operator
        if params.operator not in {"in", "out", "atop", "xor"}:
            return False

        # No arithmetic operators
        if params.operator == "arithmetic":
            return False

        # Check if using SourceAlpha as mask (common simple case)
        input_2_name = params.input_2 or "SourceAlpha"
        is_using_source_alpha = input_2_name == "SourceAlpha"

        # If using SourceAlpha, it's always simple
        if is_using_source_alpha:
            return True

        # For other masks, check if they have native DrawingML support
        if input_2 is None:
            return False

        # Check metadata first - mask must be natively supported
        if not input_2.metadata.get("native_support", True):
            return False

        # Check if mask has valid DrawingML content
        mask_fragment = (input_2.drawingml or "").strip()
        if not mask_fragment:
            return False

        # Ensure mask DrawingML is a proper effect list (starts with <a:effectLst>)
        # This guards against EMF placeholders or invalid fragments
        if not mask_fragment.startswith("<a:effectLst"):
            return False

        return True

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

        # Build outer effectLst
        outer_container = a_elem("effectDag" if enable_effect_dag else "effectLst")
        if enable_effect_dag:
            a_sub(outer_container, "cont")

        # Add base fragments
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
                    pass  # Skip if parsing fails

        # Build alpha element with inner effectLst
        alpha_elem = a_sub(outer_container, alpha_tag)
        a_sub(alpha_elem, "cont")
        inner_effectLst = a_sub(alpha_elem, "effectLst")

        # Append mask children to inner effectLst
        try:
            graft_xml_fragment(inner_effectLst, mask_children)
        except Exception:
            pass  # Skip if parsing fails

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
            opacity = float(mask.metadata.get("flood_opacity", 1.0))
        else:
            fill_meta = mask.metadata.get("fill")
            if isinstance(fill_meta, dict) and fill_meta.get("type") == "solid":
                color = str(fill_meta.get("rgb") or "").strip().lstrip("#").upper()
                opacity = float(fill_meta.get("opacity", mask.metadata.get("opacity", 1.0)))
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
                    opacity = float(mask.metadata.get("opacity", 1.0))
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
        effectLst = a_elem("effectLst")
        solidFill = a_sub(effectLst, "solidFill")
        srgbClr = a_sub(solidFill, "srgbClr", val=color)
        a_sub(srgbClr, "alpha", val=alpha)
        return to_string(effectLst)

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
        return rgb_channels_to_hex(r, g, b, scale="byte"), avg_opacity

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
