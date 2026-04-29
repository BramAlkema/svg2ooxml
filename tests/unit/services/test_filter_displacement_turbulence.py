"""Tests for displacement map and turbulence filter primitives."""

from __future__ import annotations

import struct

from lxml import etree
from tests.unit.filters.policy import assert_assets, assert_fallback, assert_strategy

from svg2ooxml.io.emf import EMFRecordType
from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.services import ConversionServices
from svg2ooxml.services.filter_service import FilterService
from svg2ooxml.services.filter_types import FilterEffectResult


def _service_with_filter(filter_xml: str) -> FilterService:
    service = FilterService()
    element = etree.fromstring(filter_xml)
    service.register_filter(element.get("id", "filter"), element)
    return service


def _records_from_hex(data_hex: str) -> list[tuple[int, bytes]]:
    data = bytes.fromhex(data_hex)
    records: list[tuple[int, bytes]] = []
    offset = 0
    length = len(data)
    while offset < length:
        record_type, size = struct.unpack_from("<II", data, offset)
        payload = data[offset + 8 : offset + size]
        records.append((record_type, payload))
        offset += size
    return records


def test_displacement_map_filter_uses_emf_fallback() -> None:
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='disp'><feDisplacementMap scale='15' xChannelSelector='R' yChannelSelector='G'/></filter>"
    )
    service.register_filter("disp", filter_xml)

    results = service.resolve_effects("disp")

    assert results
    first = results[0]
    assert isinstance(first, FilterEffectResult)
    assert_strategy(first, modern="vector")
    assert isinstance(first.effect, CustomEffect)
    assert_fallback(first, modern="emf")
    assert_assets(first, modern="emf")
    assets = first.metadata.get("fallback_assets") or []
    assert "data_hex" in assets[0]


def test_turbulence_filter_uses_emf_fallback() -> None:
    service = FilterService()
    filter_xml = etree.fromstring(
        "<filter id='turb'><feTurbulence baseFrequency='0.1 0.2' numOctaves='4' seed='2'/></filter>"
    )
    service.register_filter("turb", filter_xml)

    results = service.resolve_effects("turb")

    assert results
    first = results[0]
    assert isinstance(first, FilterEffectResult)
    assert_strategy(first, modern="vector")
    assert isinstance(first.effect, CustomEffect)
    assert_fallback(first, modern="emf")
    assert first.metadata["native_support"] is False
    assert_assets(first, modern="emf")
    assets = first.metadata.get("fallback_assets") or []
    assert "data_hex" in assets[0]


def test_palette_resolver_overrides_emf_colors() -> None:
    override_hex = "#123456"

    def resolver(filter_type: str, role: str, metadata: dict[str, object]) -> str | None:
        if filter_type == "displacement_map" and role == "background":
            return override_hex
        return None

    service = FilterService(palette_resolver=resolver)
    filter_xml = etree.fromstring(
        "<filter id='disp'><feDisplacementMap scale='12' xChannelSelector='R' yChannelSelector='G'/></filter>"
    )
    service.register_filter("disp", filter_xml)

    results = service.resolve_effects("disp")

    assert results
    assets = results[0].metadata.get("fallback_assets")
    assert isinstance(assets, list) and assets
    asset = assets[0]
    data_hex = asset["data_hex"]
    records = _records_from_hex(data_hex)
    create_brush = next(payload for code, payload in records if code == EMFRecordType.EMR_CREATEBRUSHINDIRECT)
    color_value = struct.unpack_from("<III", create_brush, 4)[1]
    expected_bgr = (
        int(override_hex[5:7], 16) << 16
        | int(override_hex[3:5], 16) << 8
        | int(override_hex[1:3], 16)
    )
    assert color_value == expected_bgr


def test_palette_resolver_binds_through_conversion_services() -> None:
    override_hex = "#0F1E2D"

    def resolver(filter_type: str, role: str, metadata: dict[str, object]) -> str | None:
        if filter_type == "displacement_map" and role == "background":
            return override_hex
        return None

    services = ConversionServices()
    services.register("filter_palette_resolver", resolver)
    filter_service = FilterService()
    services.register("filter", filter_service)

    filter_xml = etree.fromstring(
        "<filter id='disp'><feDisplacementMap scale='9' xChannelSelector='R' yChannelSelector='G'/></filter>"
    )
    filter_service.register_filter("disp", filter_xml)

    results = filter_service.resolve_effects("disp")

    assert results
    assets = results[0].metadata.get("fallback_assets")
    assert isinstance(assets, list) and assets
    asset = assets[0]
    data_hex = asset["data_hex"]
    records = _records_from_hex(data_hex)
    create_brush = next(payload for code, payload in records if code == EMFRecordType.EMR_CREATEBRUSHINDIRECT)
    color_value = struct.unpack_from("<III", create_brush, 4)[1]
    expected_bgr = (
        int(override_hex[5:7], 16) << 16
        | int(override_hex[3:5], 16) << 8
        | int(override_hex[1:3], 16)
    )
    assert color_value == expected_bgr
