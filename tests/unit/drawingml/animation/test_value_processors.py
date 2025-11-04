"""Tests for animation value processors.

Most core parsing is tested in common.conversions (137 tests).
These tests focus on animation-specific logic and delegation.
"""

import pytest

from svg2ooxml.common.units import UnitConverter
from svg2ooxml.drawingml.animation.value_processors import ValueProcessor


class TestDelegation:
    """Test that ValueProcessor correctly delegates to common.conversions."""

    def test_parse_numeric_list(self):
        result = ValueProcessor.parse_numeric_list("1 2 3")
        assert result == [1.0, 2.0, 3.0]

    def test_parse_color(self):
        result = ValueProcessor.parse_color("#FF0000")
        assert result == "FF0000"

    def test_parse_angle(self):
        result = ValueProcessor.parse_angle("45")
        assert result == 45.0

    def test_parse_scale_pair(self):
        result = ValueProcessor.parse_scale_pair("1.5")
        assert result == (1.5, 1.5)

    def test_parse_translation_pair(self):
        result = ValueProcessor.parse_translation_pair("10 20")
        assert result == (10.0, 20.0)


class TestParseOpacity:
    """Test animation-specific opacity parsing."""

    def test_opacity_zero_to_one_scale(self):
        assert ValueProcessor.parse_opacity("0.7") == "70000"
        assert ValueProcessor.parse_opacity("0.5") == "50000"
        assert ValueProcessor.parse_opacity("1.0") == "100000"
        assert ValueProcessor.parse_opacity("0.0") == "0"

    def test_opacity_percentage_scale(self):
        # Values > 1 treated as percentage
        assert ValueProcessor.parse_opacity("70") == "70000"
        assert ValueProcessor.parse_opacity("50") == "50000"
        assert ValueProcessor.parse_opacity("100") == "100000"

    def test_opacity_invalid_defaults_to_opaque(self):
        assert ValueProcessor.parse_opacity("invalid") == "100000"
        assert ValueProcessor.parse_opacity("") == "100000"

    def test_opacity_edge_cases(self):
        assert ValueProcessor.parse_opacity("0.1") == "10000"
        assert ValueProcessor.parse_opacity("0.99") == "99000"


class TestFormatPPTAngle:
    """Test angle formatting to PPT units."""

    def test_common_angles(self):
        assert ValueProcessor.format_ppt_angle(0.0) == "0"
        assert ValueProcessor.format_ppt_angle(45.0) == "2700000"
        assert ValueProcessor.format_ppt_angle(90.0) == "5400000"
        assert ValueProcessor.format_ppt_angle(180.0) == "10800000"
        assert ValueProcessor.format_ppt_angle(360.0) == "21600000"

    def test_negative_angles(self):
        assert ValueProcessor.format_ppt_angle(-45.0) == "-2700000"
        assert ValueProcessor.format_ppt_angle(-90.0) == "-5400000"

    def test_fractional_angles(self):
        result = ValueProcessor.format_ppt_angle(45.5)
        assert result == "2730000"  # 45.5 * 60000


class TestNormalizeNumericValue:
    """Test animation-specific numeric value normalization."""

    def test_angle_attributes(self):
        uc = UnitConverter()

        # All angle attribute variations
        assert ValueProcessor.normalize_numeric_value("angle", "45", unit_converter=uc) == "2700000"
        assert ValueProcessor.normalize_numeric_value("rotation", "90", unit_converter=uc) == "5400000"
        assert ValueProcessor.normalize_numeric_value("rotate", "180", unit_converter=uc) == "10800000"
        assert ValueProcessor.normalize_numeric_value("ppt_angle", "360", unit_converter=uc) == "21600000"

    def test_position_attributes_x_axis(self):
        uc = UnitConverter()

        # ppt_x uses x axis for conversion
        result = ValueProcessor.normalize_numeric_value("ppt_x", "100", unit_converter=uc)
        assert isinstance(result, str)
        # 100px at 96 DPI ≈ 914400 EMU (1 inch)
        assert int(result) > 900000

    def test_position_attributes_y_axis(self):
        uc = UnitConverter()

        # ppt_y uses y axis for conversion
        result = ValueProcessor.normalize_numeric_value("ppt_y", "100", unit_converter=uc)
        assert isinstance(result, str)
        assert int(result) > 900000

    def test_size_attributes(self):
        uc = UnitConverter()

        # ppt_w uses width axis
        result_w = ValueProcessor.normalize_numeric_value("ppt_w", "200", unit_converter=uc)
        assert isinstance(result_w, str)
        assert int(result_w) > 1800000

        # ppt_h uses height axis
        result_h = ValueProcessor.normalize_numeric_value("ppt_h", "200", unit_converter=uc)
        assert isinstance(result_h, str)
        assert int(result_h) > 1800000

    def test_line_width_attribute(self):
        uc = UnitConverter()

        # ln_w uses width axis
        result = ValueProcessor.normalize_numeric_value("ln_w", "5", unit_converter=uc)
        assert isinstance(result, str)
        assert int(result) > 0

    def test_invalid_value_returns_as_is(self):
        uc = UnitConverter()

        result = ValueProcessor.normalize_numeric_value("ppt_x", "invalid", unit_converter=uc)
        assert result == "invalid"

    def test_zero_values(self):
        uc = UnitConverter()

        assert ValueProcessor.normalize_numeric_value("ppt_angle", "0", unit_converter=uc) == "0"
        assert ValueProcessor.normalize_numeric_value("ppt_x", "0", unit_converter=uc) == "0"

    def test_negative_values(self):
        uc = UnitConverter()

        # Negative angles
        result = ValueProcessor.normalize_numeric_value("ppt_angle", "-45", unit_converter=uc)
        assert result == "-2700000"

        # Negative positions (valid in some cases)
        result = ValueProcessor.normalize_numeric_value("ppt_x", "-100", unit_converter=uc)
        assert int(result) < 0


class TestIntegration:
    """Test integrated workflows."""

    def test_parse_and_normalize_workflow(self):
        """Test typical workflow: parse → normalize."""
        uc = UnitConverter()

        # Parse angle string, then normalize
        angle_str = "45"
        angle_value = ValueProcessor.parse_angle(angle_str)
        assert angle_value == 45.0

        normalized = ValueProcessor.format_ppt_angle(angle_value)
        assert normalized == "2700000"

    def test_parse_scale_and_translate(self):
        """Test parsing transform values."""
        # Scale
        sx, sy = ValueProcessor.parse_scale_pair("1.5 2.0")
        assert sx == 1.5
        assert sy == 2.0

        # Translate
        dx, dy = ValueProcessor.parse_translation_pair("100 200")
        assert dx == 100.0
        assert dy == 200.0

        # Normalize translations to EMU
        uc = UnitConverter()
        dx_emu = ValueProcessor.normalize_numeric_value("ppt_x", str(dx), unit_converter=uc)
        dy_emu = ValueProcessor.normalize_numeric_value("ppt_y", str(dy), unit_converter=uc)

        assert int(dx_emu) > 900000  # ~1 inch
        assert int(dy_emu) > 1800000  # ~2 inches


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_strings(self):
        # Empty numeric list
        result = ValueProcessor.parse_numeric_list("")
        assert result == []

        # Empty angle returns 0
        result = ValueProcessor.parse_angle("")
        assert result == 0.0

    def test_none_color(self):
        result = ValueProcessor.parse_color(None)
        assert result == "000000"  # Default

        result = ValueProcessor.parse_color(None, default="FFFFFF")
        assert result == "FFFFFF"

    def test_scientific_notation(self):
        result = ValueProcessor.parse_numeric_list("1e2 2e3")
        assert result == [100.0, 2000.0]

    def test_very_large_values(self):
        uc = UnitConverter()

        result = ValueProcessor.normalize_numeric_value("ppt_x", "10000", unit_converter=uc)
        assert int(result) > 90000000  # ~100 inches

    def test_very_small_values(self):
        uc = UnitConverter()

        result = ValueProcessor.normalize_numeric_value("ppt_x", "0.001", unit_converter=uc)
        assert int(result) < 10000
