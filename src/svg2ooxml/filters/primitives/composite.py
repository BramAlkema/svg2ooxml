"""feComposite filter primitive."""

from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.utils.dml import extract_effect_children, is_effect_list, merge_effect_fragments

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string


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

            drawingml, fallback = self._combine_masking(params.operator, input_1, input_2)
            metadata["native_support"] = drawingml != ""
            if fallback:
                metadata["fallback_reason"] = fallback

            # Record telemetry for masking operators
            tracer = getattr(context, "tracer", None)
            if tracer:
                strategy = "native" if drawingml else "emf"

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

            return FilterResult(
                success=True,
                drawingml=drawingml,
                fallback=None if drawingml else "emf",
                metadata=metadata,
                warnings=(),
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

        # Build outer effectLst
        outer_effectLst = a_elem("effectLst")

        # Add base fragments
        if source_fragment:
            source_children = extract_effect_children(source_fragment) if is_effect_list(source_fragment) else source_fragment
            if source_children:
                # Parse and append source children to outer effectLst
                try:
                    wrapped = f'<root xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">{source_children}</root>'
                    temp_root = etree.fromstring(wrapped.encode('utf-8'))
                    for child_elem in temp_root:
                        outer_effectLst.append(child_elem)
                except Exception:
                    pass  # Skip if parsing fails

        # Build alpha element with inner effectLst
        alpha_elem = a_sub(outer_effectLst, alpha_tag)
        a_sub(alpha_elem, "cont")
        inner_effectLst = a_sub(alpha_elem, "effectLst")

        # Parse and append mask children to inner effectLst
        try:
            wrapped = f'<root xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">{mask_children}</root>'
            temp_root = etree.fromstring(wrapped.encode('utf-8'))
            for child_elem in temp_root:
                inner_effectLst.append(child_elem)
        except Exception:
            pass  # Skip if parsing fails

        return to_string(outer_effectLst), None

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
