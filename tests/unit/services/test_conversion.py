"""Tests for the conversion service container."""

from lxml import etree

from svg2ooxml.services.conversion import ConversionServices
from svg2ooxml.services.filter_service import FilterService
from svg2ooxml.services.gradient_service import GradientService
from svg2ooxml.services.image_service import ImageResource, ImageService
from svg2ooxml.services.pattern_service import PatternService
from svg2ooxml.services.setup import configure_services
from svg2ooxml.services.symbol_service import SymbolService


def test_conversion_services_register_and_resolve() -> None:
    services = ConversionServices()
    sentinel = object()
    services.register("filter", sentinel)

    assert services.filter_service is sentinel


def test_configure_services_provides_default_service_instances() -> None:
    services = configure_services()

    assert isinstance(services.filter_service, FilterService)
    assert isinstance(services.gradient_service, GradientService)
    assert isinstance(services.pattern_service, PatternService)
    assert isinstance(services.image_service, ImageService)
    assert isinstance(services.symbol_service, SymbolService)


def test_service_references_update_gradient_service() -> None:
    services = configure_services()
    gradient = etree.Element("linearGradient", id="g1")

    services.register("gradients", {"g1": gradient})

    descriptor = services.gradient_service.get("g1")
    assert descriptor is not None
    assert descriptor.gradient_id == "g1"
    assert services.gradient_service.require("g1").gradient_id == "g1"

    pattern = etree.Element("pattern", id="p1")
    services.register("patterns", {"p1": pattern})

    pattern_descriptor = services.pattern_service.get("p1")
    assert pattern_descriptor is not None
    assert pattern_descriptor.pattern_id == "p1"


def test_gradient_service_content_uses_shared_calc_offsets() -> None:
    service = GradientService()
    gradient = etree.fromstring(
        """
        <linearGradient id="grad">
          <stop offset="calc(25% + 25%)" stop-color="#000000"/>
          <stop offset="100%" stop-color="#ffffff"/>
        </linearGradient>
        """
    )

    service.register_gradient("grad", gradient)
    content = service.get_gradient_content("grad")

    assert content is not None
    assert 'pos="50000"' in content
    assert 'pos="100000"' in content


def test_gradient_service_content_uses_shared_calc_coordinates() -> None:
    service = GradientService()
    gradient = etree.fromstring(
        """
        <linearGradient id="grad" x1="0" y1="0" x2="calc(1)" y2="calc(1)">
          <stop offset="0%" stop-color="#000000"/>
          <stop offset="100%" stop-color="#ffffff"/>
        </linearGradient>
        """
    )

    service.register_gradient("grad", gradient)
    content = service.get_gradient_content("grad")

    assert content is not None
    assert 'ang="2700000"' in content


def test_pattern_service_detects_calc_rect_line() -> None:
    service = PatternService()
    pattern = etree.fromstring(
        """
        <pattern id="lines">
          <rect width="calc(8 + 2)" height="2" fill="#000000"/>
        </pattern>
        """
    )

    service.register_pattern("lines", pattern)
    content = service.get_pattern_content("lines")

    assert content is not None
    assert "pattFill" in content
    assert 'prst="horz"' in content


def test_clone_produces_isolated_services() -> None:
    services = configure_services()
    base_gradient = etree.Element("linearGradient", id="base")
    services.register("gradients", {"base": base_gradient})

    clone = services.clone()
    assert clone.gradient_service.require("base").gradient_id == "base"

    clone_gradient = etree.Element("linearGradient", id="clone")
    clone.register("gradients", {"clone": clone_gradient})

    assert "clone" in clone.gradient_service.ids()
    assert "clone" not in services.gradient_service.ids()
    assert services.gradient_service.require("base").gradient_id == "base"


def test_image_service_handles_data_uri() -> None:
    services = configure_services()
    resource = services.image_service.resolve("data:image/png;base64,Zm9v")

    assert isinstance(resource, ImageResource)
    assert resource.mime_type == "image/png"
    assert resource.data == b"foo"
