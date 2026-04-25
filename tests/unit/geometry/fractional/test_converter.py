"""Tests for fractional EMU converter."""

import pytest

from svg2ooxml.common.geometry.fractional import (
    EMU_PER_INCH,
    FractionalEMUConverter,
    PrecisionMode,
)
from svg2ooxml.common.geometry.fractional.errors import EMUBoundaryError


def test_pixels_to_emu_defaults() -> None:
    converter = FractionalEMUConverter()

    emu = converter.pixels_to_emu(96)

    assert emu == pytest.approx(EMU_PER_INCH)


def test_pixels_to_emu_rejects_non_positive_dpi() -> None:
    with pytest.raises(ValueError, match="dpi must be positive"):
        FractionalEMUConverter(dpi=0)

    converter = FractionalEMUConverter()
    with pytest.raises(ValueError, match="dpi must be positive"):
        converter.pixels_to_emu(96, dpi=-96)


def test_points_to_emu_rounding() -> None:
    converter = FractionalEMUConverter(precision_mode=PrecisionMode.HIGH)

    emu = converter.points_to_emu(12)
    rounded = converter.round_emu(emu)

    assert rounded == pytest.approx(int(emu))


def test_bounds_validation() -> None:
    converter = FractionalEMUConverter(validate_bounds=True)

    with pytest.raises(EMUBoundaryError):
        converter.inches_to_emu(1e9)


def test_precision_modes_keep_rounding_within_one_emu() -> None:
    base_value = 12.3456789  # arbitrary EMU quantity
    standard = FractionalEMUConverter(precision_mode=PrecisionMode.STANDARD)
    ultra = FractionalEMUConverter(precision_mode=PrecisionMode.ULTRA)

    std_rounded = standard.round_emu(base_value)
    ultra_rounded = ultra.round_emu(base_value)

    assert abs(std_rounded - ultra_rounded) <= 1
