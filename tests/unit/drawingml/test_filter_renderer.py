"""FilterRenderer fallback asset handling tests."""

from __future__ import annotations

from svg2ooxml.drawingml.filter_renderer import FilterRenderer
from svg2ooxml.filters.base import FilterResult


def test_filter_renderer_reuses_existing_emf_asset() -> None:
    renderer = FilterRenderer()
    metadata = {
        "filter_type": "blend",
        "fallback_assets": [
            {
                "type": "emf",
                "relationship_id": "rIdExisting",
                "width_emu": 1000,
                "height_emu": 2000,
                "data_hex": "DEADBEEF",
            }
        ],
    }
    result = FilterResult(success=True, drawingml="", fallback="emf", metadata=metadata)

    effects = renderer.render([result])

    effect_result = effects[0]
    assets = effect_result.metadata["fallback_assets"]
    assert assets[0]["relationship_id"] == "rIdExisting"
    assert renderer._emf_adapter._counter == 0  # No new placeholder generation
    assert "rIdExisting" in effect_result.effect.drawingml


def test_filter_renderer_reuses_existing_raster_asset() -> None:
    renderer = FilterRenderer()
    metadata = {
        "filter_type": "turbulence",
        "fallback_assets": [
            {
                "type": "raster",
                "relationship_id": "rIdRasterExisting",
                "width_px": 64,
                "height_px": 64,
                "data_hex": "CAFEBABE",
            }
        ],
    }
    result = FilterResult(success=True, drawingml="", fallback="raster", metadata=metadata)

    effects = renderer.render([result])

    effect_result = effects[0]
    assets = effect_result.metadata["fallback_assets"]
    assert assets[0]["relationship_id"] == "rIdRasterExisting"
    assert renderer._raster_adapter._counter == 0  # Reused asset
    assert "rIdRasterExisting" in effect_result.effect.drawingml


def test_filter_renderer_generates_emf_asset_when_missing() -> None:
    renderer = FilterRenderer()
    metadata: dict[str, object] = {"filter_type": "blend", "mode": "multiply"}
    result = FilterResult(success=True, drawingml="", fallback="emf", metadata=metadata)

    effects = renderer.render([result])

    effect_result = effects[0]
    assets = effect_result.metadata.get("fallback_assets")
    assert isinstance(assets, list) and assets
    emf_asset = assets[0]
    assert emf_asset["type"] == "emf"
    assert emf_asset["relationship_id"].startswith("rIdEmfFilter")
    assert len(emf_asset.get("data_hex", "")) > 0
    assert renderer._emf_adapter._counter >= 1
    assert emf_asset["relationship_id"] in effect_result.effect.drawingml
