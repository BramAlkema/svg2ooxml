"""FilterService scaffolding tests."""

from __future__ import annotations

import pytest
from lxml import etree

from svg2ooxml.filters.registry import FilterRegistry
from svg2ooxml.filters.resvg_bridge import ResolvedFilter, resolve_filter_element
from svg2ooxml.services.conversion import ConversionServices
from svg2ooxml.services.filter_service import FilterService


def _make_filter_element(markup: str) -> etree._Element:
    return etree.fromstring(f"<svg xmlns='http://www.w3.org/2000/svg'>{markup}</svg>")[0]


def _make_descriptor(markup: str) -> ResolvedFilter:
    return resolve_filter_element(_make_filter_element(markup))


class _NoopRegistry:
    """Simple registry stub returning no rendering results."""

    def render_filter_element(self, element, context):
        return []

    def clone(self):
        return self



def test_filter_service_registers_and_requires_definitions() -> None:
    service = FilterService()
    descriptor = _make_descriptor("<filter id='blur'/>")
    service.update_definitions({"blur": descriptor})

    fetched = service.get("blur")
    assert isinstance(fetched, ResolvedFilter)
    assert fetched.filter_id == "blur"
    assert service.require("blur").filter_id == "blur"
    assert list(service.ids()) == ["blur"]


def test_filter_service_clone_preserves_state() -> None:
    service = FilterService()
    service.register_filter("shadow", _make_descriptor("<filter id='shadow'/>"))

    clone = service.clone()
    fetched = clone.get("shadow")
    assert isinstance(fetched, ResolvedFilter)
    assert fetched.filter_id == "shadow"
    assert clone.registry is not None
    assert isinstance(clone.registry, FilterRegistry)


def test_filter_service_binds_policy_engine_from_services() -> None:
    services = ConversionServices()
    policy_engine = object()
    services.register("policy_engine", policy_engine)

    filter_defs = {"blur": _make_filter_element("<filter id='blur'/>")}
    services.register("filters", filter_defs)

    filter_service = FilterService()
    filter_service.bind_services(services)

    assert filter_service.policy_engine is policy_engine
    fetched = filter_service.get("blur")
    assert isinstance(fetched, ResolvedFilter)
    assert fetched.filter_id == "blur"


def test_descriptor_fallback_prefers_vector_hint() -> None:
    service = FilterService(registry=_NoopRegistry())
    service.register_filter("vectorish", _make_descriptor("<filter id='vectorish'><feComponentTransfer/></filter>"))
    service.set_strategy("vector")

    context = {
        "policy": {},
        "resvg_descriptor": {
            "primitive_tags": ["feComponentTransfer"],
            "primitive_count": 1,
            "filter_units": "userSpaceOnUse",
            "primitive_units": "userSpaceOnUse",
            "filter_region": {"x": 0.0, "y": 0.0, "width": 120.0, "height": 80.0},
        },
        "ir_bbox": {"x": 0.0, "y": 0.0, "width": 120.0, "height": 80.0},
    }

    results = service.resolve_effects("vectorish", context=context)

    assert results
    fallback = results[-1]
    assert fallback.strategy == "vector"
    assert fallback.fallback == "emf"
    assert fallback.metadata["descriptor"]["primitive_tags"] == ["feComponentTransfer"]
    assert fallback.metadata["bounds"]["width"] == 120.0


def test_descriptor_fallback_produces_placeholder_when_rendering_absent() -> None:
    service = FilterService(registry=_NoopRegistry())
    service.register_filter("rasterish", _make_descriptor("<filter id='rasterish'><feGaussianBlur/></filter>"))
    service.set_strategy("raster")

    context = {
        "resvg_descriptor": {
            "primitive_tags": ["feGaussianBlur"],
            "primitive_count": 1,
            "filter_units": "objectBoundingBox",
            "primitive_units": "userSpaceOnUse",
            "filter_region": {"x": None, "y": None, "width": None, "height": None},
        },
        "ir_bbox": {"x": 5.0, "y": 6.0, "width": 32.0, "height": 18.0},
    }

    results = service.resolve_effects("rasterish", context=context)

    assert results
    placeholder = results[-1]
    assert placeholder.fallback == "bitmap"
    assert placeholder.strategy in {"raster", "auto"}
    metadata = placeholder.metadata
    renderer = metadata.get("renderer")
    assert renderer in {"placeholder", "skia", "resvg", "raster"}
    if renderer == "placeholder":
        assert metadata.get("placeholder") is True
    elif renderer == "resvg":
        assert metadata.get("render_passes", 0) >= 0
        assert metadata.get("width_px", 0) > 0
        assert metadata.get("height_px", 0) > 0
    else:
        assert metadata.get("render_passes", 0) >= 1
    assets = metadata.get("fallback_assets")
    assert isinstance(assets, list) and assets[0].get("type") == "raster"


def test_raster_adapter_produces_png_asset() -> None:
    service = FilterService(registry=_NoopRegistry())
    filter_descriptor = _make_descriptor(
        "<filter id='skiaTest'><feGaussianBlur stdDeviation='8'/></filter>"
    )
    service.register_filter("skiaTest", filter_descriptor)
    service.set_strategy("raster")

    results = service.resolve_effects("skiaTest")
    assert results

    raster_effect = results[-1]
    metadata = raster_effect.metadata or {}
    assets = metadata.get("fallback_assets")
    assert isinstance(assets, list)
    raster_asset = next((asset for asset in assets if asset.get("type") == "raster"), None)
    assert raster_asset is not None
    assert raster_asset.get("format") == "png"
    raw = raster_asset.get("data")
    assert isinstance(raw, (bytes, bytearray))
    # PNG header check
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"


def test_resvg_path_returns_bitmap_result() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    descriptor = _make_descriptor(
        "<filter id='resvg'><feFlood flood-color='#336699' result='flood'/><feBlend in='SourceGraphic' in2='flood' mode='lighten'/></filter>"
    )
    service.register_filter("resvg", descriptor)

    context = {
        "ir_bbox": {"x": 0.0, "y": 0.0, "width": 32.0, "height": 24.0},
    }

    results = service.resolve_effects("resvg", context=context)

    assert results
    effect = next((result for result in results if result.strategy == "resvg"), None)
    assert effect is not None
    metadata = effect.metadata or {}
    assert metadata.get("renderer") == "resvg"
    assets = metadata.get("fallback_assets") or []
    assert assets and assets[0].get("format") == "png"


def test_legacy_strategy_skips_resvg_path() -> None:
    service = FilterService(registry=_NoopRegistry())
    service.set_strategy("legacy")
    descriptor = _make_descriptor("<filter id='legacy'><feGaussianBlur stdDeviation='2'/></filter>")
    service.register_filter("legacy", descriptor)

    results = service.resolve_effects("legacy")

    assert results
    assert all(result.strategy != "resvg" for result in results)


def test_resvg_strategy_prefers_resvg_only() -> None:
    pytest.importorskip("skia")

    service = FilterService(registry=_NoopRegistry())
    service.set_strategy("resvg")
    descriptor = _make_descriptor("<filter id='r'><feFlood flood-color='#112233'/></filter>")
    service.register_filter("r", descriptor)

    results = service.resolve_effects("r")

    assert len(results) == 1
    assert results[0].strategy == "resvg"
