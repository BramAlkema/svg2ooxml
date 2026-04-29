"""Slide orchestration helpers for multi-variant (fallback) rendering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from svg2ooxml.core.metadata import (
    merge_policy_overrides,
    set_page_variant_type,
    trace_stage_events,
    trace_totals,
)
from svg2ooxml.core.pptx_exporter_types import SvgPageSource
from svg2ooxml.policy.fidelity import DEFAULT_FIDELITY_POLICY, PolicyOverrides


@dataclass(frozen=True)
class FallbackVariant:
    """Represents a derived slide variant based on fallback decisions."""

    name: str
    policy_overrides: PolicyOverrides = field(default_factory=dict)
    title_suffix: str = ""


def derive_variants_from_trace(
    trace_report: Mapping[str, Any] | None,
    *,
    enable_split: bool,
) -> list[FallbackVariant]:
    """Inspect trace reports and derive fallback-driven slide variants."""

    if not enable_split or not trace_report:
        return []

    variants: list[FallbackVariant] = []
    seen: set[str] = set()

    def register(name: str, overrides: PolicyOverrides, suffix: str) -> None:
        if name in seen:
            return
        variants.append(
            FallbackVariant(name=name, policy_overrides=overrides, title_suffix=suffix)
        )
        seen.add(name)

    geometry_totals = trace_totals(trace_report, "geometry_totals")
    paint_totals = trace_totals(trace_report, "paint_totals")
    stage_events = trace_stage_events(trace_report)

    if geometry_totals.get("emf"):
        register(
            "geometry_emf",
            {"geometry": {"force_emf": True, "force_bitmap": False}},
            " (EMF)",
        )

    if geometry_totals.get("bitmap"):
        register(
            "geometry_bitmap",
            {"geometry": {"force_bitmap": True}},
            " (Bitmap)",
        )

    if paint_totals.get("emf") and "geometry_emf" not in seen:
        register(
            "paint_emf",
            {"geometry": {"force_emf": True, "force_bitmap": False}},
            " (Paint EMF)",
        )

    filter_fallbacks: set[str] = set()
    mask_requires_emf = False

    for event in stage_events:
        metadata = event.metadata
        if event.stage == "filter":
            fallback = metadata.get("fallback")
            if fallback is None and isinstance(metadata.get("metadata"), dict):
                fallback = metadata["metadata"].get("fallback")
            if isinstance(fallback, str):
                filter_fallbacks.add(fallback.lower())
        elif event.stage == "mask":
            if bool(metadata.get("requires_emf")):
                mask_requires_emf = True

    if mask_requires_emf:
        register(
            "mask_emf",
            {"mask": {"force_emf": True, "force_raster": False}},
            " (Mask EMF)",
        )

    if any(fallback in {"bitmap", "raster"} for fallback in filter_fallbacks):
        register(
            "filter_raster",
            {"filter": {"filter_strategy": "raster"}},
            " (Filter raster)",
        )

    if any(fallback in {"emf", "vector"} for fallback in filter_fallbacks):
        register(
            "filter_emf",
            {"filter": {"filter_strategy": "emf"}},
            " (Filter EMF)",
        )

    return variants


def build_fidelity_tier_variants() -> list[FallbackVariant]:
    """Return tiered slide variants covering direct, mimic, EMF, and bitmap output."""
    return [
        FallbackVariant(
            name=policy.name,
            policy_overrides=policy.clone_overrides(),
            title_suffix=policy.title_suffix,
        )
        for policy in DEFAULT_FIDELITY_POLICY.tiers()
    ]


def resolve_fidelity_tier_variant(name: str) -> FallbackVariant:
    """Return a single fidelity tier variant by name."""

    policy = DEFAULT_FIDELITY_POLICY.resolve_tier(name)
    return FallbackVariant(
        name=policy.name,
        policy_overrides=policy.clone_overrides(),
        title_suffix=policy.title_suffix,
    )


def expand_page_with_variants(
    page: SvgPageSource,
    variants: Sequence[FallbackVariant],
) -> list[SvgPageSource]:
    """Generate additional page sources for each variant."""

    clones: list[SvgPageSource] = []

    for variant in variants:
        metadata: dict[str, Any] = deepcopy(page.metadata or {})
        set_page_variant_type(metadata, variant.name)
        merge_policy_overrides(metadata, variant.policy_overrides)

        clones.append(
            SvgPageSource(
                svg_text=page.svg_text,
                title=(page.title or page.name or "Slide") + variant.title_suffix,
                name=f"{(page.name or 'slide')}_{variant.name}",
                metadata=metadata,
            )
        )

    return clones


__all__ = [
    "FallbackVariant",
    "build_fidelity_tier_variants",
    "derive_variants_from_trace",
    "expand_page_with_variants",
    "resolve_fidelity_tier_variant",
]
