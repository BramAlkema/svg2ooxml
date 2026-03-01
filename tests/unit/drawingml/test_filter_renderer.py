"""FilterRenderer fallback asset handling tests."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.drawingml.filter_renderer import FilterRenderer
from svg2ooxml.filters.base import FilterContext, FilterResult


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


def test_filter_renderer_preserves_effect_dag_fragment() -> None:
    renderer = FilterRenderer()
    drawingml = (
        "<a:effectDag><a:cont/><a:alphaModFix><a:cont/>"
        "<a:effectLst><a:blur/></a:effectLst></a:alphaModFix></a:effectDag>"
    )
    result = FilterResult(success=True, drawingml=drawingml, fallback=None, metadata={"filter_type": "composite"})

    effects = renderer.render([result])

    assert len(effects) == 1
    assert effects[0].effect.drawingml.startswith("<a:effectDag")
    assert "<a:effectLst><a:effectDag>" not in effects[0].effect.drawingml


def test_filter_renderer_applies_blip_enrichment_for_raster_fallback() -> None:
    renderer = FilterRenderer()
    metadata = {
        "filter_type": "color_matrix",
        "blip_color_transforms": [{"tag": "satMod", "val": 50000}],
        "fallback_assets": [{"type": "raster", "relationship_id": "rIdRasterExisting"}],
    }
    result = FilterResult(success=True, drawingml="", fallback="raster", metadata=metadata)
    context = FilterContext(
        filter_element=etree.Element("filter"),
        options={"policy": {"enable_blip_effect_enrichment": True}},
    )

    effects = renderer.render([result], context=context)

    assert len(effects) == 1
    xml = effects[0].effect.drawingml
    assert 'r:embed="rIdRasterExisting"' in xml
    assert "<a:satMod val=\"50000\"/>" in xml
    assert effects[0].metadata.get("blip_effect_enrichment_applied") is True


def test_filter_renderer_skips_blip_enrichment_when_policy_disabled() -> None:
    renderer = FilterRenderer()
    metadata = {
        "filter_type": "color_matrix",
        "blip_color_transforms": [{"tag": "satMod", "val": 50000}],
        "fallback_assets": [{"type": "raster", "relationship_id": "rIdRasterExisting"}],
    }
    result = FilterResult(success=True, drawingml="", fallback="raster", metadata=metadata)
    context = FilterContext(
        filter_element=etree.Element("filter"),
        options={"policy": {"enable_blip_effect_enrichment": False}},
    )

    effects = renderer.render([result], context=context)

    assert len(effects) == 1
    xml = effects[0].effect.drawingml
    assert "<a:satMod" not in xml


def test_filter_renderer_reads_direct_filter_policy_payload() -> None:
    renderer = FilterRenderer()
    result = FilterResult(
        success=True,
        drawingml="<a:effectLst><a:fillOverlay/></a:effectLst>",
        fallback=None,
        metadata={"filter_type": "blend"},
    )
    context = FilterContext(
        filter_element=etree.Element("filter"),
        options={"policy": {"prefer_emf_blend_modes": True}},
    )

    effects = renderer.render([result], context=context)

    assert len(effects) == 1
    assert effects[0].strategy == "vector"
