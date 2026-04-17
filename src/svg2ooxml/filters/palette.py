"""EMF palette resolution helpers for filter metadata attachment."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from svg2ooxml.services.filter_types import FilterEffectResult


def attach_emf_metadata(
    existing_results: list[FilterEffectResult],
    emf_results: list[FilterEffectResult],
) -> list[FilterEffectResult]:
    """Merge EMF fallback assets into the last vector-fallback result."""
    if not existing_results or not emf_results:
        return existing_results

    vector_indexed = [
        (index, result)
        for index, result in enumerate(existing_results)
        if result.fallback and result.fallback.lower() == "emf"
    ]
    if not vector_indexed:
        return existing_results

    base = list(existing_results)
    last_idx, last_result = vector_indexed[-1]
    metadata = dict(last_result.metadata or {})
    original_assets = list(metadata.get("fallback_assets") or [])
    assets = list(original_assets)
    descriptor_result = isinstance(last_result.metadata, dict) and last_result.metadata.get("strategy_source") == "resvg_descriptor"
    best_assets: list[dict[str, Any]] | None = None
    for emf_result in emf_results:
        emf_meta = emf_result.metadata if isinstance(emf_result.metadata, dict) else {}
        emf_assets = emf_meta.get("fallback_assets")
        if not isinstance(emf_assets, list):
            continue
        candidates = [
            asset
            for asset in emf_assets
            if isinstance(asset, dict) and asset.get("type") == "emf"
        ]
        if not candidates:
            continue
        preferred = [asset for asset in candidates if not asset.get("placeholder")]
        if preferred:
            best_assets = preferred
        else:
            best_assets = candidates

    descriptor_info = metadata.get("descriptor") if isinstance(metadata.get("descriptor"), dict) else {}
    primitive_count = None
    primitive_tags: set[str] = set()
    if isinstance(descriptor_info, dict):
        primitive_count = descriptor_info.get("primitive_count")
        tags = descriptor_info.get("primitive_tags")
        if isinstance(tags, (list, tuple, set)):
            primitive_tags = {str(tag).strip().lower() for tag in tags if tag}

    multi_stage_descriptor = descriptor_result and primitive_count and primitive_count > 1
    has_composite = descriptor_result and any("fecomposite" in tag for tag in primitive_tags)

    if descriptor_result:
        if multi_stage_descriptor or has_composite:
            raster_assets = [
                asset for asset in original_assets if isinstance(asset, dict) and asset.get("type") == "raster"
            ]
            if raster_assets:
                assets = raster_assets
            elif best_assets:
                assets = best_assets
            else:
                assets = original_assets
        else:
            assets = best_assets or original_assets
    else:
        assets = best_assets or original_assets
    metadata["fallback_assets"] = assets
    if assets:
        sample = next((asset for asset in reversed(assets) if isinstance(asset, dict)), None)
        if sample:
            sample_meta = sample.get("metadata")
            if isinstance(sample_meta, dict) and sample_meta.get("filter_type"):
                metadata["filter_type"] = sample_meta.get("filter_type")

    if assets:
        base[last_idx] = replace(
            last_result,
            metadata=metadata,
            fallback="emf",
        )
    else:
        base[last_idx] = replace(
            last_result,
            metadata=metadata,
            fallback=last_result.fallback,
        )

    return base


def attach_raster_metadata(
    existing_results: list[FilterEffectResult],
    raster_results: list[FilterEffectResult],
) -> None:
    """Attach raster fallback assets to the last existing result in-place."""
    if not existing_results:
        return
    target = existing_results[-1]
    metadata = dict(target.metadata or {})
    assets = metadata.setdefault("fallback_assets", [])
    had_emf = any(isinstance(asset, dict) and asset.get("type") == "emf" for asset in assets)
    for raster in raster_results:
        raster_meta = raster.metadata if isinstance(raster.metadata, dict) else {}
        if "renderer" in raster_meta:
            metadata.setdefault("renderer", raster_meta.get("renderer"))
        for key in ("width_px", "height_px", "filter_units", "primitive_units", "descriptor"):
            if key in raster_meta and key not in metadata:
                metadata[key] = raster_meta[key]
        for asset in raster_meta.get("fallback_assets", []) or []:
            assets.append(asset)
    if (
        metadata.get("strategy_source") == "resvg_descriptor"
        and isinstance(assets, list)
        and not had_emf
    ):
        assets.sort(key=lambda asset: 0 if isinstance(asset, dict) and asset.get("type") == "raster" else 1)
    existing_results[-1] = FilterEffectResult(
        effect=target.effect,
        strategy=target.strategy,
        metadata=metadata,
        fallback=target.fallback,
    )
