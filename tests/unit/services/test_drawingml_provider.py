"""Tests for drawingml provider wiring."""

from svg2ooxml.drawingml.generator import DrawingMLPathGenerator
from svg2ooxml.services import configure_services


def test_configure_services_registers_drawingml_generator() -> None:
    services = configure_services()

    generator = services.drawingml_path_generator

    assert isinstance(generator, DrawingMLPathGenerator)
