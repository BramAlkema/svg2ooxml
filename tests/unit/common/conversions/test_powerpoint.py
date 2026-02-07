"""Tests for unified PPTConverter class."""

import math

from svg2ooxml.common.conversions.powerpoint import PPTConverter
from svg2ooxml.common.conversions.units import DEFAULT_DPI


class TestPPTConverterInit:
    """Test PPTConverter initialization."""

    def test_default_dpi(self):
        ppt = PPTConverter()
        assert ppt.dpi == DEFAULT_DPI

    def test_custom_dpi(self):
        ppt = PPTConverter(dpi=72)
        assert ppt.dpi == 72


class TestUnitConversions:
    """Test unit conversion methods."""

    def test_px_to_emu_default_dpi(self):
        ppt = PPTConverter()
        # 1 inch at 96 DPI = 96px = 914400 EMU
        result = ppt.px_to_emu(96.0)
        assert result == 914400

    def test_px_to_emu_zero(self):
        ppt = PPTConverter()
        assert ppt.px_to_emu(0.0) == 0

    def test_px_to_emu_small_value(self):
        ppt = PPTConverter()
        result = ppt.px_to_emu(1.0)
        assert isinstance(result, int)
        assert result > 0

    def test_length_to_emu_pixels(self):
        ppt = PPTConverter()
        result = ppt.length_to_emu(96.0)
        assert result == 914400

    def test_length_to_emu_inches(self):
        ppt = PPTConverter()
        result = ppt.length_to_emu("1in")
        assert result == 914400

    def test_length_to_emu_cm(self):
        ppt = PPTConverter()
        result = ppt.length_to_emu("2.54cm")
        # 2.54cm = 1 inch = 914400 EMU
        assert abs(result - 914400) < 100  # Allow small rounding error


class TestColorConversions:
    """Test color conversion methods."""

    def test_color_to_hex_basic(self):
        ppt = PPTConverter()
        assert ppt.color_to_hex("#FF0000") == "FF0000"
        assert ppt.color_to_hex("#00FF00") == "00FF00"
        assert ppt.color_to_hex("#0000FF") == "0000FF"

    def test_color_to_hex_without_hash(self):
        ppt = PPTConverter()
        assert ppt.color_to_hex("FF0000") == "FF0000"

    def test_color_to_hex_lowercase(self):
        ppt = PPTConverter()
        assert ppt.color_to_hex("#ff0000") == "FF0000"

    def test_color_to_hex_none(self):
        ppt = PPTConverter()
        assert ppt.color_to_hex(None) == "000000"

    def test_color_to_hex_custom_default(self):
        ppt = PPTConverter()
        assert ppt.color_to_hex(None, default="FFFFFF") == "FFFFFF"


class TestAngleConversions:
    """Test angle conversion methods."""

    def test_degrees_to_ppt_zero(self):
        ppt = PPTConverter()
        assert ppt.degrees_to_ppt(0.0) == 0

    def test_degrees_to_ppt_common_angles(self):
        ppt = PPTConverter()
        assert ppt.degrees_to_ppt(45.0) == 2700000
        assert ppt.degrees_to_ppt(90.0) == 5400000
        assert ppt.degrees_to_ppt(180.0) == 10800000
        assert ppt.degrees_to_ppt(360.0) == 21600000

    def test_degrees_to_ppt_negative(self):
        ppt = PPTConverter()
        assert ppt.degrees_to_ppt(-45.0) == -2700000
        assert ppt.degrees_to_ppt(-90.0) == -5400000

    def test_radians_to_ppt_zero(self):
        ppt = PPTConverter()
        assert ppt.radians_to_ppt(0.0) == 0

    def test_radians_to_ppt_common_angles(self):
        ppt = PPTConverter()
        # π/4 = 45°
        assert abs(ppt.radians_to_ppt(math.pi / 4) - 2700000) < 10
        # π/2 = 90°
        assert abs(ppt.radians_to_ppt(math.pi / 2) - 5400000) < 10
        # π = 180°
        assert abs(ppt.radians_to_ppt(math.pi) - 10800000) < 10


class TestOpacityConversions:
    """Test opacity conversion methods."""

    def test_opacity_to_ppt_zero(self):
        ppt = PPTConverter()
        assert ppt.opacity_to_ppt(0.0) == 0

    def test_opacity_to_ppt_full(self):
        ppt = PPTConverter()
        assert ppt.opacity_to_ppt(1.0) == 100000

    def test_opacity_to_ppt_half(self):
        ppt = PPTConverter()
        assert ppt.opacity_to_ppt(0.5) == 50000

    def test_opacity_to_ppt_various(self):
        ppt = PPTConverter()
        assert ppt.opacity_to_ppt(0.25) == 25000
        assert ppt.opacity_to_ppt(0.75) == 75000
        assert ppt.opacity_to_ppt(0.7) == 70000


class TestTransformParsing:
    """Test transform parsing methods."""

    def test_parse_scale_single(self):
        ppt = PPTConverter()
        assert ppt.parse_scale("1.5") == (1.5, 1.5)
        assert ppt.parse_scale("2") == (2.0, 2.0)

    def test_parse_scale_pair(self):
        ppt = PPTConverter()
        assert ppt.parse_scale("1.5 2.0") == (1.5, 2.0)
        assert ppt.parse_scale("2 3") == (2.0, 3.0)

    def test_parse_translation(self):
        ppt = PPTConverter()
        assert ppt.parse_translation("10 20") == (10.0, 20.0)
        assert ppt.parse_translation("15.5 25.5") == (15.5, 25.5)

    def test_parse_translation_single(self):
        ppt = PPTConverter()
        assert ppt.parse_translation("10") == (10.0, 0.0)

    def test_parse_angle(self):
        ppt = PPTConverter()
        assert ppt.parse_angle("45") == 45.0
        assert ppt.parse_angle("90.5") == 90.5
        assert ppt.parse_angle("-45") == -45.0


class TestIntegration:
    """Test integrated workflows."""

    def test_complete_shape_conversion(self):
        """Test converting all properties needed for a shape."""
        ppt = PPTConverter()

        # Position
        x_emu = ppt.px_to_emu(100.0)
        y_emu = ppt.px_to_emu(200.0)
        assert isinstance(x_emu, int)
        assert isinstance(y_emu, int)

        # Size
        width_emu = ppt.px_to_emu(300.0)
        height_emu = ppt.px_to_emu(400.0)
        assert isinstance(width_emu, int)
        assert isinstance(height_emu, int)

        # Rotation
        rotation = ppt.degrees_to_ppt(45.0)
        assert rotation == 2700000

        # Fill color
        fill_color = ppt.color_to_hex("#FF0000")
        assert fill_color == "FF0000"

        # Opacity
        opacity = ppt.opacity_to_ppt(0.7)
        assert opacity == 70000

    def test_transform_workflow(self):
        """Test parsing transform string and converting values."""
        ppt = PPTConverter()

        # Parse transform components
        scale_x, scale_y = ppt.parse_scale("1.5 2.0")
        dx, dy = ppt.parse_translation("100 200")
        angle = ppt.parse_angle("45")

        # Convert angle to PPT units
        rotation = ppt.degrees_to_ppt(angle)
        assert rotation == 2700000

        # Convert translation to EMU
        dx_emu = ppt.px_to_emu(dx)
        dy_emu = ppt.px_to_emu(dy)
        assert isinstance(dx_emu, int)
        assert isinstance(dy_emu, int)

    def test_multiple_converters_independent(self):
        """Test that multiple converters work independently."""
        ppt1 = PPTConverter(dpi=96)
        ppt2 = PPTConverter(dpi=72)

        # Same pixel value should give different EMU at different DPI
        result1 = ppt1.px_to_emu(96.0)
        result2 = ppt2.px_to_emu(72.0)

        # Both should equal 1 inch = 914400 EMU
        assert result1 == 914400
        assert result2 == 914400


class TestConsistency:
    """Test consistency with direct function calls."""

    def test_degrees_consistency(self):
        """Test that PPTConverter gives same results as direct function."""
        from svg2ooxml.common.conversions.angles import degrees_to_ppt

        ppt = PPTConverter()
        for angle in [0, 45, 90, 180, 360, -45, -90]:
            assert ppt.degrees_to_ppt(angle) == degrees_to_ppt(angle)

    def test_opacity_consistency(self):
        """Test that PPTConverter gives same results as direct function."""
        from svg2ooxml.common.conversions.opacity import opacity_to_ppt

        ppt = PPTConverter()
        for opacity in [0.0, 0.25, 0.5, 0.75, 1.0]:
            assert ppt.opacity_to_ppt(opacity) == opacity_to_ppt(opacity)

    def test_color_consistency(self):
        """Test that PPTConverter gives same results as direct function."""
        from svg2ooxml.common.conversions.colors import color_to_hex

        ppt = PPTConverter()
        colors = ["#FF0000", "#00FF00", "#0000FF", "FFFFFF"]
        for color in colors:
            assert ppt.color_to_hex(color) == color_to_hex(color)
