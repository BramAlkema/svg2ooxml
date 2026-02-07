"""Structured mask analysis and geometry extraction service."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from svg2ooxml.drawingml.mask_generator import MaskGeometryResult, compute_mask_geometry
from svg2ooxml.ir.scene import MaskMode, MaskRef

DEFAULT_FALLBACK_ORDER: tuple[str, ...] = ("native", "mimic", "emf", "raster")
_POLICY_KEYS = {
    "allow_vector_mask",
    "fallback_order",
    "force_emf",
    "force_raster",
    "max_emf_segments",
    "max_emf_commands",
    "max_bitmap_area",
    "max_bitmap_side",
    "preserve_alpha_precision",
}


@dataclass(slots=True)
class MaskComputeResult:
    """Outcome of evaluating a mask reference."""

    strategy: str
    geometry: MaskGeometryResult | None = None
    diagnostics: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class MaskClassification(str, Enum):
    """Categorise mask definitions for downstream decision making."""

    MISSING = "missing"
    VECTOR = "vector"
    RASTER = "raster"
    MIXED = "mixed"
    UNSUPPORTED = "unsupported"
    EMPTY = "empty"


class StructuredMaskService:
    """Determine whether a mask can be emitted as vector geometry."""

    def __init__(self, services=None, logger: logging.Logger | None = None) -> None:
        self._services = services
        self._logger = logger or logging.getLogger(__name__)

    def compute(
        self,
        mask_ref: MaskRef | None,
        *,
        policy_options: Mapping[str, Any] | None = None,
    ) -> MaskComputeResult | None:
        if mask_ref is None:
            return None
        definition = getattr(mask_ref, "definition", None)

        classification, base_metadata, analysis_diagnostics = self._analyse_definition(definition)
        metadata: dict[str, Any] = dict(base_metadata)
        diagnostics: list[str] = list(analysis_diagnostics)
        metadata["classification"] = classification.value

        policy_info = self._normalise_policy(policy_options)
        metadata["fallback_order"] = tuple(policy_info["fallback_order"])
        if policy_info["policy_snapshot"]:
            metadata.setdefault("policy", {}).update(policy_info["policy_snapshot"])

        if classification == MaskClassification.MISSING:
            diagnostics.append("Mask definition missing; skipping mask emission.")
            metadata["strategy"] = "none"
            return MaskComputeResult(strategy="none", geometry=None, diagnostics=diagnostics, metadata=metadata)

        if classification == MaskClassification.EMPTY:
            diagnostics.append("Mask definition contains no drawable primitives; hiding masked content.")
            metadata["strategy"] = "hide"
            return MaskComputeResult(strategy="hide", geometry=None, diagnostics=diagnostics, metadata=metadata)

        if classification == MaskClassification.UNSUPPORTED:
            diagnostics.append("Mask cannot be emitted natively; falling back to vector/raster fallback path.")
            metadata["strategy"] = "unsupported"
            return MaskComputeResult(strategy="unsupported", geometry=None, diagnostics=diagnostics, metadata=metadata)

        if classification in {MaskClassification.RASTER, MaskClassification.MIXED}:
            diagnostics.append("Mask requires raster fallback due to raster content.")
            metadata.setdefault("requires_raster", True)
            metadata["strategy"] = "raster"
            return MaskComputeResult(
                strategy="raster",
                geometry=None,
                diagnostics=diagnostics,
                metadata=metadata,
            )

        # Remaining classification = VECTOR
        geometry_result = compute_mask_geometry(mask_ref)
        if geometry_result is None:
            diagnostics.append("Mask geometry unavailable; treating as unsupported.")
            metadata["classification"] = MaskClassification.UNSUPPORTED.value
            metadata["strategy"] = "unsupported"
            return MaskComputeResult(
                strategy="unsupported",
                geometry=None,
                diagnostics=diagnostics,
                metadata=metadata,
            )

        diagnostics.extend(geometry_result.diagnostics)
        if geometry_result.geometry is None:
            diagnostics.append("Failed to generate mask geometry; fallback required.")
            metadata["classification"] = MaskClassification.UNSUPPORTED.value
            metadata["strategy"] = "unsupported"
            return MaskComputeResult(
                strategy="unsupported",
                geometry=None,
                diagnostics=diagnostics,
                metadata=metadata,
            )

        bounds = geometry_result.geometry.bounds
        metadata["bounds_px"] = (bounds.x, bounds.y, bounds.width, bounds.height)
        metadata["segment_count"] = len(geometry_result.segments)
        metadata["command_count"] = len(geometry_result.commands)
        metadata["geometry_xml"] = geometry_result.geometry.xml

        final_strategy = self._determine_vector_strategy(geometry_result, metadata, policy_info, diagnostics)
        metadata["strategy"] = final_strategy

        if final_strategy == "native":
            return MaskComputeResult(
                strategy="native",
                geometry=geometry_result,
                diagnostics=diagnostics,
                metadata=metadata,
            )

        payload_geometry = geometry_result if final_strategy in {"mimic", "emf", "policy_emf"} else None
        if final_strategy in {"emf", "policy_emf"}:
            metadata.setdefault("requires_emf", True)
        if final_strategy in {"raster", "policy_raster"}:
            metadata.setdefault("requires_raster", True)
        return MaskComputeResult(
            strategy=final_strategy,
            geometry=payload_geometry,
            diagnostics=diagnostics,
            metadata=metadata,
        )

    def _analyse_definition(
        self,
        definition,
    ) -> tuple[MaskClassification, dict[str, Any], list[str]]:
        if definition is None:
            return MaskClassification.MISSING, {}, []

        diagnostics: list[str] = []
        metadata: dict[str, Any] = {}

        mode = getattr(definition, "mode", MaskMode.AUTO)
        if isinstance(mode, MaskMode):
            metadata["mode"] = mode.value
        else:
            metadata["mode"] = mode or MaskMode.AUTO.value

        metadata["mask_units"] = getattr(definition, "mask_units", None)
        metadata["mask_content_units"] = getattr(definition, "mask_content_units", None)

        unsupported_reasons: list[str] = []

        if isinstance(mode, MaskMode) and mode == MaskMode.ALPHA:
            diagnostics.append("Alpha mask mode detected; native vector masks support luminance only.")
            unsupported_reasons.append("alpha_mode")

        content_fragments = tuple(
            fragment.lower() for fragment in self._as_sequence(getattr(definition, "content_xml", ()))
        )
        raster_features = self._detect_raster_features(content_fragments)
        has_raster = bool(raster_features)
        if has_raster:
            metadata["raster_features"] = sorted(raster_features)

        if any("<mask" in fragment for fragment in content_fragments):
            diagnostics.append("Nested mask usage detected; not supported for native emission.")
            unsupported_reasons.append("nested_mask")

        unit_issues = self._detect_unit_conflicts(
            getattr(definition, "mask_units", None), getattr(definition, "mask_content_units", None)
        )
        if unit_issues:
            diagnostics.extend(unit_issues)
            unsupported_reasons.append("unit_conflict")

        has_vector = bool(getattr(definition, "segments", ())) or bool(getattr(definition, "primitives", ()))
        metadata["has_vector_content"] = has_vector
        metadata["has_raster_content"] = has_raster

        if unsupported_reasons:
            metadata["unsupported_reasons"] = unsupported_reasons
            return MaskClassification.UNSUPPORTED, metadata, diagnostics

        if has_raster and has_vector:
            diagnostics.append("Mask combines vector geometry with raster/filter content.")
            return MaskClassification.MIXED, metadata, diagnostics
        if has_raster:
            diagnostics.append("Mask contains raster-only content.")
            return MaskClassification.RASTER, metadata, diagnostics
        if has_vector:
            return MaskClassification.VECTOR, metadata, diagnostics

        diagnostics.append("Mask definition contains no drawable primitives.")
        return MaskClassification.EMPTY, metadata, diagnostics

    @staticmethod
    def _detect_raster_features(fragments: Sequence[str]) -> set[str]:
        features: set[str] = set()
        for fragment in fragments:
            if "<image" in fragment:
                features.add("image")
            if "<pattern" in fragment:
                features.add("pattern")
            if "<lineargradient" in fragment or "<radialgradient" in fragment:
                features.add("gradient")
            if "<filter" in fragment or "<fe" in fragment:
                features.add("filter")
            if "<foreignobject" in fragment:
                features.add("foreignObject")
        return features

    @staticmethod
    def _detect_unit_conflicts(mask_units: Any, content_units: Any) -> list[str]:
        messages: list[str] = []
        supported = {None, "userspaceonuse", "objectboundingbox"}
        if isinstance(mask_units, str) and mask_units.lower() not in supported:
            messages.append(f"maskUnits='{mask_units}' is not supported for native emission.")
        if isinstance(content_units, str) and content_units.lower() not in supported:
            messages.append(f"maskContentUnits='{content_units}' is not supported for native emission.")
        return messages

    @staticmethod
    def _as_sequence(value: Any) -> Iterable[Any]:
        if value is None:
            return ()
        if isinstance(value, (list, tuple)):
            return value
        return (value,)

    def _normalise_policy(self, policy_options: Mapping[str, Any] | None) -> dict[str, Any]:
        order: list[str] = list(DEFAULT_FALLBACK_ORDER)
        allow_vector = True
        force_emf = False
        force_raster = False
        max_emf_segments: int | None = None
        max_emf_commands: int | None = None
        max_bitmap_area: int | None = None
        max_bitmap_side: int | None = None
        preserve_alpha = True
        snapshot: dict[str, Any] = {}

        if policy_options:
            raw_order = policy_options.get("fallback_order")
            if isinstance(raw_order, str):
                raw_order = [part.strip() for part in raw_order.split(",") if part.strip()]
            if isinstance(raw_order, Sequence):
                cleaned = [str(item).lower() for item in raw_order]
                filtered = [item for item in cleaned if item in {"native", "mimic", "emf", "raster"}]
                if filtered:
                    order = filtered

            allow_vector = bool(policy_options.get("allow_vector_mask", allow_vector))
            force_emf = bool(policy_options.get("force_emf", force_emf))
            force_raster = bool(policy_options.get("force_raster", force_raster))
            max_emf_segments = self._coerce_int(policy_options.get("max_emf_segments"))
            max_emf_commands = self._coerce_int(policy_options.get("max_emf_commands"))
            max_bitmap_area = self._coerce_int(policy_options.get("max_bitmap_area"))
            max_bitmap_side = self._coerce_int(policy_options.get("max_bitmap_side"))
            if "preserve_alpha_precision" in policy_options:
                preserve_alpha = bool(policy_options.get("preserve_alpha_precision"))

            snapshot = {key: policy_options[key] for key in _POLICY_KEYS if key in policy_options}
            snapshot.setdefault("fallback_order", tuple(order))

        return {
            "fallback_order": order,
            "allow_vector_mask": allow_vector,
            "force_emf": force_emf,
            "force_raster": force_raster,
            "max_emf_segments": max_emf_segments,
            "max_emf_commands": max_emf_commands,
            "max_bitmap_area": max_bitmap_area,
            "max_bitmap_side": max_bitmap_side,
            "preserve_alpha_precision": preserve_alpha,
            "policy_snapshot": snapshot,
        }

    def _determine_vector_strategy(
        self,
        geometry_result: MaskGeometryResult,
        metadata: dict[str, Any],
        policy_info: dict[str, Any],
        diagnostics: list[str],
    ) -> str:
        order: list[str] = policy_info["fallback_order"]
        allow_vector = policy_info["allow_vector_mask"]
        force_emf = policy_info["force_emf"]
        force_raster = policy_info["force_raster"]
        max_emf_segments = policy_info["max_emf_segments"]
        max_emf_commands = policy_info["max_emf_commands"]

        if force_raster:
            metadata.setdefault("requires_raster", True)
            diagnostics.append("Mask policy forces raster fallback.")
            return "policy_raster"
        if force_emf:
            metadata.setdefault("requires_emf", True)
            diagnostics.append("Mask policy forces EMF fallback.")
            return "policy_emf"

        vector_disabled = not allow_vector

        for option in order:
            choice = option.lower()
            if choice == "native":
                if vector_disabled:
                    continue
                return "native"
            if choice == "mimic":
                if vector_disabled:
                    continue
                if geometry_result.geometry is None:
                    diagnostics.append("Mask mimic fallback skipped: vector geometry unavailable.")
                    continue
                metadata["mimic_supported"] = True
                return "mimic"
            if choice == "emf":
                strategy_name = "policy_emf" if vector_disabled else "emf"
                seg_count = len(geometry_result.segments)
                cmd_count = len(geometry_result.commands)
                if max_emf_segments is not None and seg_count > max_emf_segments:
                    diagnostics.append(
                        f"Mask EMF fallback skipped: segment count {seg_count} exceeds limit {max_emf_segments}."
                    )
                    continue
                if max_emf_commands is not None and cmd_count > max_emf_commands:
                    diagnostics.append(
                        f"Mask EMF fallback skipped: command count {cmd_count} exceeds limit {max_emf_commands}."
                    )
                    continue
                metadata.setdefault("requires_emf", True)
                return strategy_name
            if choice == "raster":
                strategy_name = "policy_raster" if vector_disabled else "raster"
                metadata.setdefault("requires_raster", True)
                return strategy_name

        metadata.setdefault("requires_raster", True)
        diagnostics.append("Mask policy fallback order exhausted; using raster fallback.")
        return "raster"

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            ivalue = int(value)
        except (TypeError, ValueError):
            return None
        return ivalue


__all__ = ["StructuredMaskService", "MaskComputeResult"]
