from __future__ import annotations

import pytest

pytest.importorskip("skia")

from lxml import etree

from svg2ooxml.filters.resvg_bridge import resolve_filter_element
from svg2ooxml.services.conversion import ConversionServices
from svg2ooxml.services.filter_service import FilterService


def _filter_element(markup: str) -> etree._Element:
    return etree.fromstring(f"<svg xmlns='http://www.w3.org/2000/svg'>{markup}</svg>")[0]


def test_filter_raster_fallback_uses_resvg_renderer() -> None:
    services = ConversionServices()
    filter_service = FilterService()
    filter_service.bind_services(services)

    descriptor = resolve_filter_element(
        _filter_element(
            "<filter id='noise'><feTurbulence baseFrequency='0.1' numOctaves='2' seed='2'/></filter>"
        )
    )
    filter_service.register_filter("noise", descriptor)
    filter_service.set_strategy("resvg-only")

    context = {
        "resvg_descriptor": {
            "primitive_tags": ["feTurbulence"],
            "primitive_count": 1,
            "filter_units": "objectBoundingBox",
            "primitive_units": "userSpaceOnUse",
            "filter_region": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
        },
        "ir_bbox": {"x": 0.0, "y": 0.0, "width": 64.0, "height": 48.0},
    }

    effects = filter_service.resolve_effects("noise", context=context)
    assert effects, "Expected filter fallback effects"
    raster_effect = effects[-1]
    metadata = raster_effect.metadata or {}
    assert metadata.get("renderer") in {"resvg", "skia"}
    if metadata.get("renderer") == "resvg":
        assets = metadata.get("fallback_assets") or []
        assert assets, "resvg renderer should provide fallback assets"
        asset_types = {asset.get("type") for asset in assets}
        assert asset_types & {"raster", "emf"}, "resvg fallback should include raster or EMF asset"
        raster_asset = next((asset for asset in assets if asset.get("type") == "raster"), None)
        if raster_asset is not None:
            assert raster_asset.get("format") == "png"
            assert raster_asset.get("data", b"")[:8] == b"\x89PNG\r\n\x1a\n"
