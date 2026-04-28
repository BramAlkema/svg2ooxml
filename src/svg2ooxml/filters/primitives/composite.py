"""feComposite filter primitive."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.filters.base import Filter, FilterContext, FilterResult
from svg2ooxml.filters.primitives.composite_inputs import CompositeInputMixin
from svg2ooxml.filters.primitives.composite_masking import CompositeMaskingMixin
from svg2ooxml.filters.primitives.composite_over import CompositeOverMixin
from svg2ooxml.filters.primitives.composite_types import (
    SUPPORTED_OPERATORS,
    CompositeParams,
)


class CompositeFilter(
    CompositeInputMixin,
    CompositeOverMixin,
    CompositeMaskingMixin,
    Filter,
):
    primitive_tags = ("feComposite",)
    filter_type = "composite"

    def apply(self, primitive: etree._Element, context: FilterContext) -> FilterResult:
        params = self._parse_params(primitive)
        pipeline = context.pipeline_state or {}
        input_1_name = params.input_1 or "SourceGraphic"
        input_2_name = params.input_2 or (
            "SourceAlpha" if params.operator in {"in", "out"} else "SourceGraphic"
        )

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

            tracer = getattr(context, "tracer", None)
            if tracer:
                if drawingml:
                    strategy = "native"
                elif fallback in {"mask_empty", "mask_missing_effects", "missing_mask"}:
                    strategy = "raster"
                else:
                    strategy = "emf"

                reason_parts = [f"Masking operator '{params.operator}'"]
                mask_kind = "simple mask" if is_simple else "complex mask"
                if drawingml:
                    reason_parts.append(f"{mask_kind} → alpha compositing")
                else:
                    reason_parts.append(f"{mask_kind} → fallback={fallback}")
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
                    fallback_mode = (
                        "bitmap"
                        if (approximation_allowed or prefer_rasterization)
                        else "emf"
                    )
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

        if input_1 is not None or input_2 is not None:
            metadata["native_support"] = False
            metadata["fallback_reason"] = f"operator:{params.operator}"

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


__all__ = ["CompositeFilter", "CompositeParams", "SUPPORTED_OPERATORS"]
