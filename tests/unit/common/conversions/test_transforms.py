"""Tests for transform parsing utilities."""

import pytest

from svg2ooxml.common.conversions.transforms import (
    parse_angle,
    parse_angle_strict,
    parse_numeric_list,
    parse_scale_pair,
    parse_strict_numeric_list,
    parse_translation_pair,
)


class TestParseNumericList:
    """Test parse_numeric_list function."""

    def test_empty_string(self):
        assert parse_numeric_list("") == []

    def test_single_number(self):
        assert parse_numeric_list("42") == [42.0]
        assert parse_numeric_list("3.14") == [3.14]

    def test_space_separated(self):
        assert parse_numeric_list("1 2 3") == [1.0, 2.0, 3.0]
        assert parse_numeric_list("1.5 2.5 3.5") == [1.5, 2.5, 3.5]

    def test_comma_separated(self):
        assert parse_numeric_list("1,2,3") == [1.0, 2.0, 3.0]
        assert parse_numeric_list("1.5,2.5,3.5") == [1.5, 2.5, 3.5]

    def test_mixed_separators(self):
        assert parse_numeric_list("1, 2, 3") == [1.0, 2.0, 3.0]
        assert parse_numeric_list("1.5, 2.5 3.5") == [1.5, 2.5, 3.5]

    def test_negative_numbers(self):
        assert parse_numeric_list("-1 -2 -3") == [-1.0, -2.0, -3.0]
        assert parse_numeric_list("-1.5 2.5 -3.5") == [-1.5, 2.5, -3.5]

    def test_scientific_notation(self):
        assert parse_numeric_list("1e2") == [100.0]
        assert parse_numeric_list("1.5e-2") == [0.015]
        assert parse_numeric_list("1e2 2e3") == [100.0, 2000.0]

    def test_leading_plus_sign(self):
        assert parse_numeric_list("+1 +2") == [1.0, 2.0]
        assert parse_numeric_list("+1.5e2") == [150.0]

    def test_whitespace_handling(self):
        assert parse_numeric_list("  1   2   3  ") == [1.0, 2.0, 3.0]
        assert parse_numeric_list("\t1\n2\r3") == [1.0, 2.0, 3.0]

    def test_calc_numbers_are_single_values(self):
        assert parse_numeric_list("calc(1 + 2)") == [3.0]
        assert parse_numeric_list("10 calc(2 * 3), -5") == [10.0, 6.0, -5.0]
        assert parse_numeric_list("calc((1 + 2) * 3)") == [9.0]

    def test_invalid_calc_preserves_historical_number_extraction(self):
        assert parse_numeric_list("calc(1px + 2px)") == [1.0, 2.0]
        assert parse_numeric_list("calc(1 + 2") == [1.0, 2.0]


class TestParseStrictNumericList:
    """Test strict numeric list parsing shared by viewBox-like grammars."""

    def test_accepts_compact_signed_values(self):
        assert parse_strict_numeric_list("-10-20 100 50") == [-10.0, -20.0, 100.0, 50.0]

    def test_rejects_non_separator_garbage(self):
        with pytest.raises(ValueError, match="numeric list contains non-numeric values"):
            parse_strict_numeric_list("garbage 0 0 100 50")

    def test_rejects_trailing_garbage(self):
        with pytest.raises(ValueError, match="numeric list contains non-numeric values"):
            parse_strict_numeric_list("0 0 100 50px")

    def test_accepts_calc_when_enabled(self):
        assert parse_strict_numeric_list(
            "0 calc(1 + 2), 10-5",
            allow_calc=True,
        ) == [0.0, 3.0, 10.0, -5.0]

    def test_rejects_calc_when_disabled(self):
        with pytest.raises(ValueError, match="numeric list contains non-numeric values"):
            parse_strict_numeric_list("0 calc(1 + 2)")

    def test_rejects_invalid_calc_list(self):
        with pytest.raises(ValueError, match="numeric list contains non-numeric values"):
            parse_strict_numeric_list("0 calc(1px + 2px)", allow_calc=True)


class TestParseScalePair:
    """Test parse_scale_pair function."""

    def test_single_value(self):
        assert parse_scale_pair("1.5") == (1.5, 1.5)
        assert parse_scale_pair("2") == (2.0, 2.0)

    def test_two_values(self):
        assert parse_scale_pair("1.5 2.0") == (1.5, 2.0)
        assert parse_scale_pair("2 3") == (2.0, 3.0)

    def test_comma_separated(self):
        assert parse_scale_pair("1.5,2.0") == (1.5, 2.0)
        assert parse_scale_pair("2,3") == (2.0, 3.0)

    def test_more_than_two_values(self):
        # Should take first two
        assert parse_scale_pair("1 2 3") == (1.0, 2.0)
        assert parse_scale_pair("1.5 2.5 3.5") == (1.5, 2.5)

    def test_empty_string(self):
        assert parse_scale_pair("") == (1.0, 1.0)

    def test_negative_values(self):
        assert parse_scale_pair("-1.5") == (-1.5, -1.5)
        assert parse_scale_pair("-1.5 2.0") == (-1.5, 2.0)

    def test_scientific_notation(self):
        assert parse_scale_pair("1.5e2") == (150.0, 150.0)
        assert parse_scale_pair("1e-1 2e-1") == (0.1, 0.2)


class TestParseTranslationPair:
    """Test parse_translation_pair function."""

    def test_two_values(self):
        assert parse_translation_pair("10 20") == (10.0, 20.0)
        assert parse_translation_pair("15.5 25.5") == (15.5, 25.5)

    def test_single_value(self):
        # Should return (value, 0.0)
        assert parse_translation_pair("10") == (10.0, 0.0)
        assert parse_translation_pair("15.5") == (15.5, 0.0)

    def test_empty_string(self):
        assert parse_translation_pair("") == (0.0, 0.0)

    def test_comma_separated(self):
        assert parse_translation_pair("10,20") == (10.0, 20.0)
        assert parse_translation_pair("15.5,25.5") == (15.5, 25.5)

    def test_more_than_two_values(self):
        # Should take first two
        assert parse_translation_pair("10 20 30") == (10.0, 20.0)
        assert parse_translation_pair("15.5 25.5 35.5") == (15.5, 25.5)

    def test_negative_values(self):
        assert parse_translation_pair("-10 20") == (-10.0, 20.0)
        assert parse_translation_pair("10 -20") == (10.0, -20.0)
        assert parse_translation_pair("-10 -20") == (-10.0, -20.0)

    def test_scientific_notation(self):
        assert parse_translation_pair("1e2 2e2") == (100.0, 200.0)
        assert parse_translation_pair("1.5e-1 2.5e-1") == (0.15, 0.25)

    def test_calc_values(self):
        assert parse_translation_pair("calc(5 + 5), calc(4 * 5)") == (10.0, 20.0)


class TestParseAngle:
    """Test parse_angle function."""

    def test_integer_angle(self):
        assert parse_angle("45") == 45.0
        assert parse_angle("90") == 90.0
        assert parse_angle("180") == 180.0

    def test_float_angle(self):
        assert parse_angle("45.5") == 45.5
        assert parse_angle("90.25") == 90.25

    def test_negative_angle(self):
        assert parse_angle("-45") == -45.0
        assert parse_angle("-90.5") == -90.5

    def test_zero_angle(self):
        assert parse_angle("0") == 0.0

    def test_empty_string(self):
        assert parse_angle("") == 0.0

    def test_scientific_notation(self):
        assert parse_angle("4.5e1") == 45.0
        assert parse_angle("9e1") == 90.0

    def test_multiple_values(self):
        # Should take first value
        assert parse_angle("45 90") == 45.0
        assert parse_angle("45.5 90.5") == 45.5

    def test_positive_sign(self):
        assert parse_angle("+45") == 45.0
        assert parse_angle("+90.5") == 90.5

    def test_css_angle_units(self):
        assert parse_angle("0.25turn") == 90.0
        assert parse_angle("100grad") == 90.0
        assert parse_angle("1.5707963267948966rad") == pytest.approx(90.0)

    def test_css_angle_calc(self):
        assert parse_angle("calc(1turn - 90deg)") == pytest.approx(270.0)
        assert parse_angle("calc(100grad + 90deg)") == pytest.approx(180.0)
        assert parse_angle("calc(45 + 45)") == pytest.approx(90.0)

    def test_invalid_css_angle_calc_falls_back(self):
        assert parse_angle("calc(1deg + 2px)") == 1.0

    def test_strict_angle_rejects_loose_fallback_values(self):
        assert parse_angle_strict("0.25turn") == pytest.approx(90.0)
        assert parse_angle_strict("calc(45 + 45)") == pytest.approx(90.0)
        assert parse_angle_strict("calc(1deg + 2px)") is None
        assert parse_angle_strict("45 90") is None


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_whitespace_only(self):
        assert parse_numeric_list("   \t\n  ") == []
        assert parse_scale_pair("   ") == (1.0, 1.0)
        assert parse_translation_pair("   ") == (0.0, 0.0)
        assert parse_angle("   ") == 0.0

    def test_very_large_numbers(self):
        result = parse_numeric_list("1e10 2e10")
        assert result == [1e10, 2e10]

    def test_very_small_numbers(self):
        result = parse_numeric_list("1e-10 2e-10")
        assert abs(result[0] - 1e-10) < 1e-15
        assert abs(result[1] - 2e-10) < 1e-15

    def test_zero_values(self):
        assert parse_scale_pair("0 0") == (0.0, 0.0)
        assert parse_translation_pair("0 0") == (0.0, 0.0)
        assert parse_angle("0") == 0.0
