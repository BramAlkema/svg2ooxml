"""Slide orchestration helpers for multi-variant (fallback) rendering."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.pptx_exporter import SvgPageSource


@dataclass(frozen=True)
class FallbackVariant:
    """Represents a derived slide variant based on fallback decisions."""

    name: str
    policy_overrides: dict[str, dict[str, object]] = field(default_factory=dict)
    title_suffix: str = ""


def derive_variants_from_trace(
    trace_report: dict[str, object] | None,
    *,
    enable_split: bool,
) -> list[FallbackVariant]:
    """Inspect trace reports and derive fallback-driven slide variants."""

    if not enable_split or not trace_report:
        return []

    variants: list[FallbackVariant] = []
    seen: set[str] = set()

    def register(name: str, overrides: dict[str, dict[str, object]], suffix: str) -> None:
        if name in seen:
            return
        variants.append(FallbackVariant(name=name, policy_overrides=overrides, title_suffix=suffix))
        seen.add(name)

    geometry_totals: dict[str, int] = trace_report.get("geometry_totals", {})  # type: ignore[assignment]
    paint_totals: dict[str, int] = trace_report.get("paint_totals", {})  # type: ignore[assignment]
    stage_events: list[dict[str, object]] = trace_report.get("stage_events", [])  # type: ignore[assignment]

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
        stage = event.get("stage")
        metadata: dict[str, object] = event.get("metadata") or {}
        if stage == "filter":
            fallback = metadata.get("fallback")
            if fallback is None and isinstance(metadata.get("metadata"), dict):
                fallback = metadata["metadata"].get("fallback")  # type: ignore[index]
            if isinstance(fallback, str):
                filter_fallbacks.add(fallback.lower())
        elif stage == "mask":
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

    base_vector_overrides = {
        "geometry": {
            "allow_emf_fallback": False,
            "allow_bitmap_fallback": False,
            "simplify_paths": False,
        },
        "filter": {"strategy": "native"},
        "mask": {
            "allow_vector_mask": True,
            "force_emf": False,
            "force_raster": False,
        },
        "clip": {},
    }

    tiers = [
        (
            "direct",
            " (Direct)",
            {
                **base_vector_overrides,
                "mask": {**base_vector_overrides["mask"], "fallback_order": ("native",)},
                "clip": {"fallback_order": ("native",)},
            },
        ),
        (
            "mimic",
            " (Mimic)",
            {
                **base_vector_overrides,
                "geometry": {
                    **base_vector_overrides["geometry"],
                    "simplify_paths": True,
                },
                "mask": {**base_vector_overrides["mask"], "fallback_order": ("native", "mimic")},
                "clip": {"fallback_order": ("native", "mimic")},
            },
        ),
        (
            "emf",
            " (EMF)",
            {
                "geometry": {
                    "allow_emf_fallback": True,
                    "allow_bitmap_fallback": False,
                },
                "filter": {"strategy": "emf"},
                "mask": {
                    "allow_vector_mask": True,
                    "force_emf": False,
                    "force_raster": False,
                    "fallback_order": ("native", "mimic", "emf"),
                },
                "clip": {"fallback_order": ("native", "mimic", "emf")},
            },
        ),
        (
            "bitmap",
            " (Bitmap)",
            {
                "geometry": {
                    "allow_emf_fallback": True,
                    "allow_bitmap_fallback": True,
                },
                "filter": {"strategy": "raster"},
                "mask": {
                    "allow_vector_mask": True,
                    "force_emf": False,
                    "force_raster": False,
                    "fallback_order": ("native", "mimic", "emf", "raster"),
                },
                "clip": {"fallback_order": ("native", "mimic", "emf", "raster")},
            },
        ),
    ]

    variants: list[FallbackVariant] = []
    for name, suffix, overrides in tiers:
        variants.append(
            FallbackVariant(
                name=name,
                policy_overrides=overrides,
                title_suffix=suffix,
            )
        )

    return variants


def expand_page_with_variants(
    page: SvgPageSource,
    variants: Sequence[FallbackVariant],
) -> list[SvgPageSource]:
    """Generate additional page sources for each variant."""

    clones: list[SvgPageSource] = []

    for variant in variants:
        metadata: dict[str, Any] = dict(page.metadata or {})
        variant_meta = metadata.setdefault("variant", {})
        variant_meta["type"] = variant.name
        policy_bucket = metadata.setdefault("policy_overrides", {})
        for category, overrides in variant.policy_overrides.items():
            merged = dict(policy_bucket.get(category, {}))
            merged.update(overrides)
            policy_bucket[category] = merged

        from svg2ooxml.core.pptx_exporter import SvgPageSource

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
]
