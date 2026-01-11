"""Tests for conversion context wiring helpers."""

from svg2ooxml.common.style.resolver import StyleResolver
from svg2ooxml.common.units import UnitConverter
from svg2ooxml.core.conversion_context import build_conversion_context
from svg2ooxml.core.parser.preprocess.services import build_parser_services
from svg2ooxml.services import ConversionServices


def test_build_conversion_context_reuses_style_resolver() -> None:
    services = ConversionServices()
    unit_converter = UnitConverter()
    style_resolver = StyleResolver(unit_converter)
    services.register("unit_converter", unit_converter)
    services.register("style_resolver", style_resolver)

    context = build_conversion_context(services=services)

    assert context.unit_converter is unit_converter
    assert context.style_resolver is style_resolver
    assert context.services.resolve("style_resolver") is style_resolver


def test_conversion_context_clone_copies_policy_context() -> None:
    context = build_conversion_context()
    clone = context.clone()

    assert clone.policy_context is not context.policy_context
    assert clone.policy_context.selections == context.policy_context.selections


def test_build_parser_services_registers_unit_converter() -> None:
    parser_services = build_parser_services()

    assert parser_services.unit_converter is not None
    assert parser_services.style_resolver is not None
    assert parser_services.services.resolve("unit_converter") is parser_services.unit_converter
    assert parser_services.services.resolve("style_resolver") is parser_services.style_resolver
