from __future__ import annotations

from svg2ooxml.filters.metadata import (
    coerce_fallback_asset,
    collect_fallback_asset_payloads,
    fallback_asset_bytes,
    fallback_asset_data_hex,
)


def test_coerce_fallback_asset_filters_asset_type_and_bad_shapes() -> None:
    asset = {
        "type": "emf",
        "relationship_id": "rIdEmf1",
        "data_hex": "DEADBEEF",
        1: "ignored",
    }

    assert coerce_fallback_asset(asset, asset_type="raster") is None
    coerced = coerce_fallback_asset(asset, asset_type="emf")

    assert coerced == {
        "type": "emf",
        "relationship_id": "rIdEmf1",
        "data_hex": "DEADBEEF",
    }


def test_fallback_asset_data_helpers_normalize_payloads() -> None:
    raw_asset = {"type": "raster", "data": b"\xca\xfe"}
    invalid_hex = {"type": "raster", "data_hex": "not hex"}

    assert fallback_asset_data_hex(raw_asset) == "cafe"
    assert raw_asset["data_hex"] == "cafe"
    assert fallback_asset_bytes(raw_asset) == b"\xca\xfe"
    assert fallback_asset_data_hex(invalid_hex) is None
    assert "data_hex" not in invalid_hex


def test_collect_fallback_asset_payloads_validates_list_items() -> None:
    metadata = {
        "fallback_assets": [
            {"type": "emf", "relationship_id": "rIdEmf1"},
            {"type": "raster", "data_hex": "CAFE"},
            {"type": "raster", "data_hex": "bad"},
            "ignored",
        ]
    }

    assets = collect_fallback_asset_payloads(
        metadata,
        asset_type="raster",
        require_data=True,
    )

    assert assets == [{"type": "raster", "data_hex": "CAFE"}]
