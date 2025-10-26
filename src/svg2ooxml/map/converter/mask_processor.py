"""Mask processing bridge for IR elements."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from svg2ooxml.ir.scene import MaskDefinition, MaskInstance, MaskMode, MaskRef
from svg2ooxml.services.mask_service import StructuredMaskService

try:  # pragma: no cover - typing guard
    from svg2ooxml.map.tracer import ConversionTracer
except Exception:  # pragma: no cover
    ConversionTracer = None  # type: ignore


@dataclass
class MaskProcessingResult:
    """Outcome of evaluating mask usage for an IR element."""

    requires_emf: bool
    xml_fragment: str = ""
    media_files: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def with_metadata(self, **extra: Any) -> "MaskProcessingResult":
        combined = dict(self.metadata)
        combined.update(extra)
        return MaskProcessingResult(
            requires_emf=self.requires_emf,
            xml_fragment=self.xml_fragment,
            media_files=list(self.media_files),
            metadata=combined,
        )


class MaskProcessor:
    """Inspect mask references and capture mapper hints."""

    def __init__(self, services=None) -> None:
        self._services = services
        self._logger = logging.getLogger(__name__)
        mask_service = None
        if services is not None:
            mask_service = getattr(services, "mask_service", None)
            if mask_service is None and hasattr(services, "resolve"):
                mask_service = services.resolve("mask_service")
        mask_assets = None
        if services is not None:
            mask_assets = getattr(services, "mask_asset_store", None)
            if mask_assets is None and hasattr(services, "resolve"):
                mask_assets = services.resolve("mask_asset_store")
        self._mask_service: StructuredMaskService = mask_service or StructuredMaskService(services)
        self._mask_asset_store = mask_assets
        self._tracer: "ConversionTracer | None" = None

    def set_tracer(self, tracer: "ConversionTracer | None") -> None:
        self._tracer = tracer

    def process(
        self,
        ir_element,
        *,
        policy_options: Mapping[str, Any] | None = None,
    ) -> MaskProcessingResult:
        mask_ref = getattr(ir_element, "mask", None)
        mask_instance = getattr(ir_element, "mask_instance", None)
        if mask_ref is None and isinstance(mask_instance, MaskInstance):
            mask_ref = mask_instance.mask
        if mask_ref is None:
            return MaskProcessingResult(requires_emf=False)

        metadata = self._build_metadata(mask_ref, mask_instance, ir_element)
        policy_summary = self._summarize_policy(policy_options)
        if policy_summary:
            policy_bucket = metadata.setdefault("policy", {})
            policy_bucket.setdefault("mask", {}).update(policy_summary)

        service_result = self._mask_service.compute(mask_ref, policy_options=policy_options)
        requires_emf = True
        xml_fragment = ""

        if service_result is not None:
            service_policy = dict(service_result.metadata.get("policy", {}))
            other_meta = {k: v for k, v in service_result.metadata.items() if k != "policy"}
            metadata.update(other_meta)
            if service_policy:
                policy_bucket = metadata.setdefault("policy", {})
                policy_bucket.update(service_policy)
            if service_result.diagnostics:
                diagnostics = metadata.setdefault("diagnostics", [])
                diagnostics.extend(service_result.diagnostics)

            strategy = metadata.get("strategy", getattr(service_result, "strategy", None))
            if strategy in {"raster", "policy_raster"}:
                metadata.setdefault("requires_raster", True)

            if service_result.strategy == "native" and service_result.geometry is not None:
                requires_emf = False
                xml_fragment = service_result.geometry.geometry.xml
            else:
                requires_emf = True
        else:
            requires_emf = True

        metadata.setdefault("requires_emf", requires_emf)

        if requires_emf:
            self._logger.debug(
                "Mask detected on %s; forcing EMF fallback. mask_id=%s missing_definition=%s",
                type(ir_element).__name__,
                getattr(mask_ref, "mask_id", None),
                metadata.get("missing_definition"),
            )
        else:
            self._logger.debug(
                "Mask detected on %s; emitting native geometry. mask_id=%s",
                type(ir_element).__name__,
                getattr(mask_ref, "mask_id", None),
            )

        tracer = self._tracer
        if tracer is not None and mask_ref is not None:
            decision = "emf" if requires_emf else "native"
            tracer.record_geometry_decision(
                tag="mask",
                decision=decision,
                metadata=dict(metadata),
                element_id=getattr(mask_ref, "mask_id", None),
            )
            tracer.record_stage_event(
                stage="mask",
                action="processed",
                subject=getattr(mask_ref, "mask_id", None),
                metadata={
                    "requires_emf": requires_emf,
                    "strategy": metadata.get("strategy"),
                    "diagnostics": metadata.get("diagnostics"),
                },
            )

        return MaskProcessingResult(requires_emf=requires_emf, xml_fragment=xml_fragment, metadata=metadata)

    def _build_metadata(
        self,
        mask_ref: MaskRef,
        mask_instance: MaskInstance | None,
        ir_element,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "mask_id": mask_ref.mask_id,
        }

        definition: Optional[MaskDefinition] = getattr(mask_ref, "definition", None)
        if definition is not None:
            metadata.update(
                {
                    "definition_id": definition.mask_id,
                    "mask_type": getattr(definition.mask_type, "value", definition.mask_type),
                    "mask_mode": definition.mode.value if isinstance(definition.mode, MaskMode) else definition.mode,
                    "mask_units": definition.mask_units,
                    "mask_content_units": definition.mask_content_units,
                    "opacity": definition.opacity,
                    "segments": definition.segments,
                    "bounding_box": definition.bounding_box,
                    "transform": definition.transform,
                    "content_xml": definition.content_xml,
                    "mask_region": definition.region,
                    "raw_region": dict(definition.raw_region),
                }
            )
            if definition.policy_hints:
                metadata.setdefault("policy_hints", {}).update(dict(definition.policy_hints))
        else:
            metadata["missing_definition"] = True

        if mask_ref.target_bounds is not None:
            metadata.setdefault("target_bounds", mask_ref.target_bounds)
        if mask_ref.target_opacity is not None:
            metadata.setdefault("target_opacity", mask_ref.target_opacity)
        if mask_ref.policy_hints:
            metadata.setdefault("policy_hints", {}).update(dict(mask_ref.policy_hints))

        if isinstance(mask_instance, MaskInstance):
            if mask_instance.bounds is not None:
                metadata.setdefault("instance_bounds", mask_instance.bounds)
            if mask_instance.opacity is not None:
                metadata.setdefault("instance_opacity", mask_instance.opacity)
            if mask_instance.diagnostics:
                metadata.setdefault("diagnostics", []).extend(mask_instance.diagnostics)
            if mask_instance.policy_hints:
                metadata.setdefault("policy_hints", {}).update(dict(mask_instance.policy_hints))

        element_type = type(ir_element).__name__ if ir_element is not None else None
        if element_type:
            metadata.setdefault("element_type", element_type)

        if getattr(ir_element, "clip", None) is not None:
            metadata.setdefault("clip_present", True)

        if hasattr(ir_element, "segments"):
            try:
                metadata.setdefault("segment_count", len(getattr(ir_element, "segments")))
            except TypeError:
                pass
        if hasattr(ir_element, "opacity"):
            try:
                metadata.setdefault("element_opacity", float(getattr(ir_element, "opacity")))
            except (TypeError, ValueError):
                pass
        if hasattr(ir_element, "bbox"):
            try:
                metadata.setdefault("element_bbox", getattr(ir_element, "bbox"))
            except Exception:  # pragma: no cover - defensive
                pass

        return metadata

    @staticmethod
    def _summarize_policy(options: Mapping[str, Any] | None) -> dict[str, Any]:
        if not options:
            return {}

        summary: dict[str, Any] = {}
        fallback = options.get("fallback_order")
        if fallback is not None:
            if isinstance(fallback, (list, tuple)):
                summary["fallback_order"] = tuple(fallback)
            else:
                summary["fallback_order"] = fallback
        allow_vector = options.get("allow_vector_mask")
        if allow_vector is not None:
            summary["allow_vector_mask"] = bool(allow_vector)
        for key in ("force_emf", "force_raster", "max_emf_segments", "max_emf_commands", "max_bitmap_area", "max_bitmap_side", "preserve_alpha_precision"):
            if key in options:
                summary[key] = options[key]

        return summary

__all__ = ["MaskProcessor", "MaskProcessingResult"]
