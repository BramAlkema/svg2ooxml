"""Tests for service setup idempotence and overrides."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.services.image_service import ImageService
from svg2ooxml.services.providers import registry as provider_registry
from svg2ooxml.services.setup import configure_services


def test_configure_services_returns_fresh_instances() -> None:
    first = configure_services()
    second = configure_services()

    assert first is not second
    assert set(first.services.keys()) == set(second.services.keys())

    for name in first.services:
        first_service = first.services[name]
        second_service = second.services[name]
        assert type(first_service) is type(second_service)
        assert first_service is not second_service


def test_configure_services_overrides_without_defaults() -> None:
    override_a = ImageService()
    services_a = configure_services(include_defaults=False, image=override_a)
    assert set(services_a.services.keys()) == {
        "image",
        "image_processor",
        "emf_path_adapter",
        "mask_processor",
        "mask_asset_store",
        "smart_font_converter",
        "clip_service",
        "mask_service",
    }
    assert services_a.image_service is override_a
    assert services_a.resolve("image_processor") is not None
    assert services_a.mask_processor is not None
    assert services_a.emf_path_adapter is not None
    assert services_a.smart_font_converter is not None
    assert services_a.clip_service is not None
    assert services_a.mask_service is not None

    override_b = ImageService()
    services_b = configure_services(include_defaults=False, image=override_b)
    assert set(services_b.services.keys()) == {
        "image",
        "image_processor",
        "emf_path_adapter",
        "mask_processor",
        "mask_asset_store",
        "smart_font_converter",
        "clip_service",
        "mask_service",
    }
    assert services_b.image_service is override_b
    assert services_b.resolve("image_processor") is not None
    assert services_b.mask_processor is not None
    assert services_b.emf_path_adapter is not None
    assert services_b.smart_font_converter is not None
    assert services_b.clip_service is not None
    assert services_b.mask_service is not None


def test_provider_registry_stable_after_configuration() -> None:
    configure_services()
    snapshot = {name for name, _factory in provider_registry.iter_providers()}

    configure_services()
    assert {name for name, _factory in provider_registry.iter_providers()} == snapshot


def test_configure_services_applies_filter_strategy() -> None:
    services = configure_services(filter_strategy="raster")
    filter_service = services.filter_service
    assert filter_service is not None

    assert getattr(filter_service, "_strategy") == "raster"
