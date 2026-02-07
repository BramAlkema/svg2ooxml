"""Tests for angle conversion utilities."""

import math

from svg2ooxml.common.conversions.angles import (
    PPT_ANGLE_SCALE,
    degrees_to_ppt,
    ppt_to_degrees,
    ppt_to_radians,
    radians_to_ppt,
)


class TestDegreesToPPT:
    """Test degrees_to_ppt conversion."""

    def test_zero_degrees(self):
        assert degrees_to_ppt(0.0) == 0

    def test_common_angles(self):
        assert degrees_to_ppt(45.0) == 2700000
        assert degrees_to_ppt(90.0) == 5400000
        assert degrees_to_ppt(180.0) == 10800000
        assert degrees_to_ppt(360.0) == 21600000

    def test_negative_angles(self):
        assert degrees_to_ppt(-45.0) == -2700000
        assert degrees_to_ppt(-90.0) == -5400000

    def test_fractional_degrees(self):
        assert degrees_to_ppt(45.5) == 2730000
        assert degrees_to_ppt(0.001) == 60


class TestPPTToDegrees:
    """Test ppt_to_degrees conversion."""

    def test_zero(self):
        assert ppt_to_degrees(0) == 0.0

    def test_common_angles(self):
        assert ppt_to_degrees(2700000) == 45.0
        assert ppt_to_degrees(5400000) == 90.0
        assert ppt_to_degrees(10800000) == 180.0
        assert ppt_to_degrees(21600000) == 360.0

    def test_negative(self):
        assert ppt_to_degrees(-2700000) == -45.0


class TestRadiansToPPT:
    """Test radians_to_ppt conversion."""

    def test_zero_radians(self):
        assert radians_to_ppt(0.0) == 0

    def test_common_angles(self):
        # π/4 = 45°
        assert abs(radians_to_ppt(math.pi / 4) - 2700000) < 10
        # π/2 = 90°
        assert abs(radians_to_ppt(math.pi / 2) - 5400000) < 10
        # π = 180°
        assert abs(radians_to_ppt(math.pi) - 10800000) < 10
        # 2π = 360°
        assert abs(radians_to_ppt(2 * math.pi) - 21600000) < 10


class TestPPTToRadians:
    """Test ppt_to_radians conversion."""

    def test_zero(self):
        assert ppt_to_radians(0) == 0.0

    def test_common_angles(self):
        # 45° = π/4
        assert abs(ppt_to_radians(2700000) - math.pi / 4) < 0.0001
        # 90° = π/2
        assert abs(ppt_to_radians(5400000) - math.pi / 2) < 0.0001
        # 180° = π
        assert abs(ppt_to_radians(10800000) - math.pi) < 0.0001


class TestRoundtrip:
    """Test roundtrip conversions."""

    def test_degrees_roundtrip(self):
        """Test degrees → ppt → degrees."""
        for degrees in [0, 45, 90, 135, 180, 225, 270, 315, 360]:
            ppt = degrees_to_ppt(degrees)
            result = ppt_to_degrees(ppt)
            assert abs(result - degrees) < 0.001, f"Failed for {degrees} degrees"

    def test_radians_roundtrip(self):
        """Test radians → ppt → radians."""
        for radians in [0, math.pi / 4, math.pi / 2, math.pi, 2 * math.pi]:
            ppt = radians_to_ppt(radians)
            result = ppt_to_radians(ppt)
            assert abs(result - radians) < 0.0001, f"Failed for {radians} radians"


class TestConstants:
    """Test module constants."""

    def test_ppt_angle_scale(self):
        assert PPT_ANGLE_SCALE == 60000
