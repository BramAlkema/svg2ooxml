"""Tests for scale and position conversion utilities."""

from svg2ooxml.common.conversions.scale import (
    PPT_SCALE,
    position_to_ppt,
    scale_to_ppt,
)


class TestScaleToPPT:
    """Test scale_to_ppt conversion."""

    def test_identity(self):
        assert scale_to_ppt(1.0) == 100000

    def test_zero(self):
        assert scale_to_ppt(0.0) == 0

    def test_half(self):
        assert scale_to_ppt(0.5) == 50000

    def test_double(self):
        assert scale_to_ppt(2.0) == 200000

    def test_negative(self):
        assert scale_to_ppt(-1.0) == -100000

    def test_fractional_rounding(self):
        assert scale_to_ppt(0.333333) == 33333
        assert scale_to_ppt(0.666667) == 66667


class TestPositionToPPT:
    """Test position_to_ppt conversion."""

    def test_zero(self):
        assert position_to_ppt(0.0) == 0

    def test_one(self):
        assert position_to_ppt(1.0) == 100000

    def test_half(self):
        assert position_to_ppt(0.5) == 50000

    def test_clamps_above_one(self):
        assert position_to_ppt(1.5) == 100000

    def test_clamps_below_zero(self):
        assert position_to_ppt(-0.5) == 0

    def test_fractional_rounding(self):
        assert position_to_ppt(0.333333) == 33333
        assert position_to_ppt(0.666667) == 66667


class TestConstants:
    """Test module constants."""

    def test_ppt_scale(self):
        assert PPT_SCALE == 100000
