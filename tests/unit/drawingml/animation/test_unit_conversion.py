"""Tests for AnimationUnitConverter."""

from __future__ import annotations

import pytest

from svg2ooxml.drawingml.animation.unit_conversion import (
    PPT_ANGLE_FACTOR,
    PPT_OPACITY_FACTOR,
    PPT_SCALE_FACTOR,
    AnimationUnitConverter,
)


@pytest.fixture
def uc() -> AnimationUnitConverter:
    return AnimationUnitConverter()


# ------------------------------------------------------------------ #
# Constants                                                           #
# ------------------------------------------------------------------ #


def test_ppt_angle_factor():
    assert PPT_ANGLE_FACTOR == 60_000


def test_ppt_opacity_factor():
    assert PPT_OPACITY_FACTOR == 100_000


def test_ppt_scale_factor():
    assert PPT_SCALE_FACTOR == 100_000


# ------------------------------------------------------------------ #
# opacity_to_ppt                                                      #
# ------------------------------------------------------------------ #


class TestOpacityToPpt:
    def test_fully_opaque(self, uc: AnimationUnitConverter):
        assert uc.opacity_to_ppt(1.0) == 100_000

    def test_fully_transparent(self, uc: AnimationUnitConverter):
        assert uc.opacity_to_ppt(0.0) == 0

    def test_half(self, uc: AnimationUnitConverter):
        assert uc.opacity_to_ppt(0.5) == 50_000

    def test_seventy_percent(self, uc: AnimationUnitConverter):
        assert uc.opacity_to_ppt(0.7) == 70_000

    def test_clamps_above_one(self, uc: AnimationUnitConverter):
        assert uc.opacity_to_ppt(1.5) == 100_000

    def test_clamps_below_zero(self, uc: AnimationUnitConverter):
        assert uc.opacity_to_ppt(-0.3) == 0


# ------------------------------------------------------------------ #
# degrees_to_ppt                                                      #
# ------------------------------------------------------------------ #


class TestDegreesToPpt:
    def test_zero(self, uc: AnimationUnitConverter):
        assert uc.degrees_to_ppt(0.0) == 0

    def test_45_degrees(self, uc: AnimationUnitConverter):
        assert uc.degrees_to_ppt(45.0) == 2_700_000

    def test_90_degrees(self, uc: AnimationUnitConverter):
        assert uc.degrees_to_ppt(90.0) == 5_400_000

    def test_360_degrees(self, uc: AnimationUnitConverter):
        assert uc.degrees_to_ppt(360.0) == 21_600_000

    def test_negative(self, uc: AnimationUnitConverter):
        assert uc.degrees_to_ppt(-90.0) == -5_400_000


# ------------------------------------------------------------------ #
# px_to_emu                                                           #
# ------------------------------------------------------------------ #


class TestPxToEmu:
    def test_one_inch_at_96dpi(self, uc: AnimationUnitConverter):
        # 96px at 96dpi = 1 inch = 914400 EMU
        assert uc.px_to_emu(96.0) == 914_400

    def test_zero(self, uc: AnimationUnitConverter):
        assert uc.px_to_emu(0.0) == 0

    def test_100px(self, uc: AnimationUnitConverter):
        # 100px at 96dpi = 100/96 inches = 952500 EMU
        result = uc.px_to_emu(100.0)
        assert isinstance(result, int)
        assert result == 952_500

    def test_returns_int(self, uc: AnimationUnitConverter):
        result = uc.px_to_emu(33.3)
        assert isinstance(result, int)


# ------------------------------------------------------------------ #
# scale_to_ppt                                                        #
# ------------------------------------------------------------------ #


class TestScaleToPpt:
    def test_identity(self, uc: AnimationUnitConverter):
        assert uc.scale_to_ppt(1.0) == 100_000

    def test_double(self, uc: AnimationUnitConverter):
        assert uc.scale_to_ppt(2.0) == 200_000

    def test_half(self, uc: AnimationUnitConverter):
        assert uc.scale_to_ppt(0.5) == 50_000

    def test_zero(self, uc: AnimationUnitConverter):
        assert uc.scale_to_ppt(0.0) == 0


# ------------------------------------------------------------------ #
# px_to_slide_fraction                                                #
# ------------------------------------------------------------------ #


class TestPxToSlideFraction:
    def test_full_slide_width(self):
        # Standard slide: 9144000 EMU wide. 96px/inch, 10 inches = 960px.
        uc = AnimationUnitConverter()
        # 960px at 96dpi = 10 inches = 9144000 EMU → fraction = 1.0
        result = uc.px_to_slide_fraction(960.0, axis="x")
        assert abs(result - 1.0) < 1e-6

    def test_half_slide_height(self):
        uc = AnimationUnitConverter()
        # Standard slide: 6858000 EMU tall = 7.5 inches = 720px at 96dpi
        result = uc.px_to_slide_fraction(360.0, axis="y")
        assert abs(result - 0.5) < 1e-6

    def test_zero(self):
        uc = AnimationUnitConverter()
        assert uc.px_to_slide_fraction(0.0, axis="x") == 0.0

    def test_custom_slide_size(self):
        uc = AnimationUnitConverter(
            slide_width_emu=12_192_000,  # widescreen 16:9
            slide_height_emu=6_858_000,
        )
        # 12192000 EMU = 13.333 inches = 1280px at 96dpi
        result = uc.px_to_slide_fraction(1280.0, axis="x")
        assert abs(result - 1.0) < 1e-6


# ------------------------------------------------------------------ #
# normalize_attribute_value                                           #
# ------------------------------------------------------------------ #


class TestNormalizeAttributeValue:
    def test_angle_attribute(self, uc: AnimationUnitConverter):
        assert uc.normalize_attribute_value("ppt_angle", "45") == "2700000"

    def test_x_position(self, uc: AnimationUnitConverter):
        result = uc.normalize_attribute_value("ppt_x", "100")
        assert result == "952500"

    def test_non_numeric_passthrough(self, uc: AnimationUnitConverter):
        assert uc.normalize_attribute_value("ppt_x", "auto") == "auto"

    def test_rotation_alias(self, uc: AnimationUnitConverter):
        assert uc.normalize_attribute_value("rotation", "90") == "5400000"
