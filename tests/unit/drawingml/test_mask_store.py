"""Tests for the mask asset store."""

from __future__ import annotations

from svg2ooxml.drawingml.mask_store import MaskAssetStore


def test_register_vector_mask_deduplicates_by_geometry() -> None:
    store = MaskAssetStore()

    first = store.register_vector_mask(
        mask_id="mask1",
        geometry_xml="<a:mask id='m1'/>",
        mode="luminance",
    )
    second = store.register_vector_mask(
        mask_id="mask2",
        geometry_xml="<a:mask id='m1'/>",
        mode="luminance",
    )

    assert first.asset_id == second.asset_id
    assets = list(store.iter_assets())
    assert len(assets) == 1
    asset = assets[0]
    assert asset.relationship_id.startswith("rIdMask")
    assert asset.geometry_hash is not None
    assert asset.sources == {"mask1", "mask2"}


def test_register_raster_mask_allocates_unique_part() -> None:
    store = MaskAssetStore()

    handle = store.register_raster_mask(
        mask_id="mask-raster",
        image_bytes=b"fake-bytes",
        mode="alpha",
        image_format="png",
    )

    assert handle.kind == "raster"
    assert handle.content_type == "image/png"
    asset = next(store.iter_assets())
    assert asset.part_name.endswith(".png")
    assert asset.data == b"fake-bytes"


def test_clone_returns_independent_store() -> None:
    store = MaskAssetStore()
    store.register_vector_mask(mask_id="mask1", geometry_xml="<mask/>", mode="luminance")

    cloned = store.clone()
    assert len(list(cloned.iter_assets())) == 1

    cloned.register_vector_mask(mask_id="mask2", geometry_xml="<mask/>", mode="alpha")
    assert len(list(store.iter_assets())) == 1
    assert len(list(cloned.iter_assets())) == 2


def test_clear_resets_registry() -> None:
    store = MaskAssetStore()
    store.register_vector_mask(mask_id="mask1", geometry_xml="<mask/>", mode="luminance")
    store.clear()
    assert list(store.iter_assets()) == []
    handle = store.register_vector_mask(mask_id="mask2", geometry_xml="<mask/>", mode="luminance")
    assert handle.relationship_id.endswith("1")
