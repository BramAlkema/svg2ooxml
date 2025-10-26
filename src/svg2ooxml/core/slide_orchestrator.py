"""Slide orchestration helpers for multi-variant (fallback) rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.core.pptx_exporter import SvgPageSource


@dataclass(frozen=True)
class FallbackVariant:
    """Represents a derived slide variant based on fallback decisions."""

    name: str
    policy_overrides: Dict[str, Dict[str, object]] = field(default_factory=dict)
    title_suffix: str = ""


def derive_variants_from_trace(
    trace_report: Dict[str, object] | None,
    *,
    enable_split: bool,
) -> List[FallbackVariant]:
    """Inspect trace reports and derive fallback-driven slide variants."""

    if not enable_split or not trace_report:
        return []

    variants: list[FallbackVariant] = []
    seen: set[str] = set()

    def register(name: str, overrides: Dict[str, Dict[str, object]], suffix: str) -> None:
        if name in seen:
            return
        variants.append(FallbackVariant(name=name, policy_overrides=overrides, title_suffix=suffix))
        seen.add(name)

    geometry_totals: Dict[str, int] = trace_report.get("geometry_totals", {})  # type: ignore[assignment]
    paint_totals: Dict[str, int] = trace_report.get("paint_totals", {})  # type: ignore[assignment]
    stage_events: List[Dict[str, object]] = trace_report.get("stage_events", [])  # type: ignore[assignment]

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
        metadata: Dict[str, object] = event.get("metadata") or {}
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


def expand_page_with_variants(
    page: "SvgPageSource",
    variants: Sequence[FallbackVariant],
) -> List["SvgPageSource"]:
    """Generate additional page sources for each variant."""

    clones: list["SvgPageSource"] = []

    for variant in variants:
        metadata: Dict[str, Any] = dict(page.metadata or {})
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


__all__ = ["FallbackVariant", "derive_variants_from_trace", "expand_page_with_variants"]
