from __future__ import annotations

from svg2ooxml.filters.palette import attach_emf_metadata, attach_raster_metadata
from svg2ooxml.services.filter_types import FilterEffectResult


def _effect(
    *,
    fallback: str | None,
    metadata: dict[str, object] | None = None,
) -> FilterEffectResult:
    return FilterEffectResult(
        effect=None,
        strategy="vector",
        fallback=fallback,
        metadata=metadata or {},
    )


def test_attach_emf_metadata_dedupes_and_copies_assets() -> None:
    asset = {"type": "emf", "relationship_id": "rIdEmf1", "data_hex": "DEADBEEF"}
    existing = [_effect(fallback="emf", metadata={"fallback_assets": [asset]})]
    source = [_effect(fallback="emf", metadata={"fallback_assets": [asset, asset]})]

    merged = attach_emf_metadata(existing, source)
    assets = merged[-1].metadata["fallback_assets"]

    assert assets == [asset]
    assert assets[0] is not asset


def test_attach_raster_metadata_filters_nondict_assets_and_dedupes() -> None:
    existing = [_effect(fallback="bitmap", metadata={})]
    raster_asset = {"type": "raster", "relationship_id": "rIdRaster1"}
    raster_results = [
        _effect(
            fallback="bitmap",
            metadata={
                "renderer": "raster",
                "fallback_assets": [raster_asset, "bad", raster_asset],
            },
        )
    ]

    attach_raster_metadata(existing, raster_results)

    assert existing[-1].metadata["renderer"] == "raster"
    assert existing[-1].metadata["fallback_assets"] == [raster_asset]
