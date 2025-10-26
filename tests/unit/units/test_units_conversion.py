"""Tests for unit conversion helpers."""

import pytest

from svg2ooxml.units.conversion import (
    ConversionContext,
    UnitConverter,
    DEFAULT_DPI,
    EMU_PER_INCH,
    emu_to_px,
    emu_to_unit,
    px_to_emu,
)


def test_to_emu_pixels() -> None:
    converter = UnitConverter()
    context = converter.create_context(width=800, height=600)

    result = converter.to_emu("96px", context)

    assert result == EMU_PER_INCH


def test_to_emu_percentage_x() -> None:
    converter = UnitConverter()
    context = converter.create_context(width=100, height=50)

    result = converter.to_emu("50%", context, axis="x")

    assert result == pytest.approx(50 * EMU_PER_INCH / DEFAULT_DPI, rel=1e-6)


def test_to_emu_em_units() -> None:
    converter = UnitConverter()
    context = converter.create_context(width=100, height=100, font_size=16)

    result = converter.to_emu("2em", context)

    assert result == 2 * 16 * EMU_PER_INCH / DEFAULT_DPI


def test_to_px_supports_absolute_units() -> None:
    converter = UnitConverter(dpi=96.0)
    context = converter.create_context(width=10, height=10)

    assert converter.to_px("2.54cm", context) == pytest.approx(96.0)
    assert converter.to_px("72pt", context) == pytest.approx(96.0)


def test_context_derivation_sets_parent_dimensions() -> None:
    converter = UnitConverter()
    root = converter.create_context(width=400, height=300, font_size=12)
    child = root.derive(width=200, height=100)

    assert child.parent_width == pytest.approx(400.0)
    assert child.parent_height == pytest.approx(300.0)


def test_px_to_emu_roundtrip() -> None:
    px = 32.5
    emu = px_to_emu(px)
    back = emu_to_px(emu)

    assert back == pytest.approx(px, rel=1e-6)


def test_emu_to_unit_conversions() -> None:
    inches = 2.0
    emu_value = inches * EMU_PER_INCH

    assert emu_to_unit(emu_value, "in") == pytest.approx(inches)
    assert emu_to_unit(emu_value, "cm") == pytest.approx(inches * 2.54)
