"""Tests for unit conversion helpers."""

import pytest

from svg2ooxml.parser.units import UnitConverter, viewbox_to_px


def test_unit_converter_handles_known_units() -> None:
    converter = UnitConverter()

    assert converter.to_px("1in") == 96.0
    assert converter.to_px("2cm") == pytest.approx(75.590551, rel=1e-6)


def test_unit_converter_falls_back_to_px() -> None:
    converter = UnitConverter()

    assert converter.to_px("42") == 42.0
    assert converter.to_px("5", fallback_unit="pt") == pytest.approx(6.666666, rel=1e-6)


def test_viewbox_to_px_returns_scale_factors() -> None:
    sx, sy = viewbox_to_px((0, 0, 100, 50), width=200, height=100)

    assert sx == 2.0
    assert sy == 2.0
