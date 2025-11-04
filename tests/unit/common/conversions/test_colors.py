"""Tests for color conversion utilities."""

import pytest

from svg2ooxml.common.conversions.colors import (
    color_to_hex,
    hex_to_rgb,
    rgb_to_hex,
)


class TestHexToRGB:
    """Test hex_to_rgb conversion."""

    def test_basic_colors(self):
        assert hex_to_rgb("#FF0000") == (255, 0, 0)
        assert hex_to_rgb("#00FF00") == (0, 255, 0)
        assert hex_to_rgb("#0000FF") == (0, 0, 255)

    def test_without_hash(self):
        assert hex_to_rgb("FF0000") == (255, 0, 0)
        assert hex_to_rgb("00FF00") == (0, 255, 0)
        assert hex_to_rgb("0000FF") == (0, 0, 255)

    def test_lowercase(self):
        assert hex_to_rgb("#ff0000") == (255, 0, 0)
        assert hex_to_rgb("ff0000") == (255, 0, 0)

    def test_mixed_case(self):
        assert hex_to_rgb("#FfAaBb") == (255, 170, 187)
        assert hex_to_rgb("FfAaBb") == (255, 170, 187)

    def test_black_and_white(self):
        assert hex_to_rgb("#000000") == (0, 0, 0)
        assert hex_to_rgb("#FFFFFF") == (255, 255, 255)

    def test_gray_values(self):
        assert hex_to_rgb("#808080") == (128, 128, 128)
        assert hex_to_rgb("#C0C0C0") == (192, 192, 192)

    def test_invalid_length(self):
        with pytest.raises(ValueError, match="Invalid hex color"):
            hex_to_rgb("#FFF")
        with pytest.raises(ValueError, match="Invalid hex color"):
            hex_to_rgb("#FFFFFFF")
        with pytest.raises(ValueError, match="Invalid hex color"):
            hex_to_rgb("")

    def test_invalid_characters(self):
        with pytest.raises(ValueError):
            hex_to_rgb("#GGGGGG")
        with pytest.raises(ValueError):
            hex_to_rgb("#XXYYZZ")


class TestRGBToHex:
    """Test rgb_to_hex conversion."""

    def test_basic_colors(self):
        assert rgb_to_hex(255, 0, 0) == "FF0000"
        assert rgb_to_hex(0, 255, 0) == "00FF00"
        assert rgb_to_hex(0, 0, 255) == "0000FF"

    def test_black_and_white(self):
        assert rgb_to_hex(0, 0, 0) == "000000"
        assert rgb_to_hex(255, 255, 255) == "FFFFFF"

    def test_gray_values(self):
        assert rgb_to_hex(128, 128, 128) == "808080"
        assert rgb_to_hex(192, 192, 192) == "C0C0C0"

    def test_mixed_values(self):
        assert rgb_to_hex(255, 170, 187) == "FFAABB"
        assert rgb_to_hex(123, 45, 67) == "7B2D43"

    def test_clamping_above_255(self):
        assert rgb_to_hex(300, 0, 0) == "FF0000"
        assert rgb_to_hex(0, 300, 0) == "00FF00"
        assert rgb_to_hex(0, 0, 300) == "0000FF"
        assert rgb_to_hex(300, 300, 300) == "FFFFFF"

    def test_clamping_below_zero(self):
        assert rgb_to_hex(-10, 0, 0) == "000000"
        assert rgb_to_hex(0, -10, 0) == "000000"
        assert rgb_to_hex(0, 0, -10) == "000000"
        assert rgb_to_hex(-10, -10, -10) == "000000"

    def test_float_values(self):
        # Should handle floats by converting to int
        assert rgb_to_hex(255.9, 0.1, 0.5) == "FF0000"
        assert rgb_to_hex(127.5, 127.5, 127.5) == "7F7F7F"

    def test_zero_padding(self):
        # Ensure small values are zero-padded
        assert rgb_to_hex(1, 2, 3) == "010203"
        assert rgb_to_hex(10, 20, 30) == "0A141E"


class TestColorToHex:
    """Test color_to_hex conversion."""

    def test_hex_colors(self):
        assert color_to_hex("#FF0000") == "FF0000"
        assert color_to_hex("#00FF00") == "00FF00"
        assert color_to_hex("#0000FF") == "0000FF"

    def test_hex_without_hash(self):
        assert color_to_hex("FF0000") == "FF0000"
        assert color_to_hex("00FF00") == "00FF00"

    def test_lowercase_hex(self):
        # Should normalize to uppercase
        assert color_to_hex("#ff0000") == "FF0000"
        assert color_to_hex("ff0000") == "FF0000"

    def test_named_colors(self):
        # Named colors depend on parse_color implementation
        # These tests assume parse_color handles common named colors
        result = color_to_hex("red")
        assert isinstance(result, str)
        assert len(result) == 6

    def test_rgb_colors(self):
        # RGB colors depend on parse_color implementation
        result = color_to_hex("rgb(255, 0, 0)")
        assert isinstance(result, str)
        assert len(result) == 6

    def test_none_color(self):
        assert color_to_hex(None) == "000000"
        assert color_to_hex(None, default="FFFFFF") == "FFFFFF"

    def test_empty_string(self):
        # Should use default
        assert color_to_hex("") == "000000"
        assert color_to_hex("", default="FFFFFF") == "FFFFFF"

    def test_custom_default(self):
        assert color_to_hex(None, default="AABBCC") == "AABBCC"
        assert color_to_hex("invalid", default="112233") == "112233"

    def test_transparent_color(self):
        # Transparent should use default
        result = color_to_hex("transparent")
        assert isinstance(result, str)
        assert len(result) == 6


class TestRoundtrip:
    """Test roundtrip conversions."""

    def test_hex_to_rgb_to_hex(self):
        """Test hex → RGB → hex."""
        test_colors = [
            "FF0000",
            "00FF00",
            "0000FF",
            "FFFFFF",
            "000000",
            "808080",
            "FFAABB",
            "123456",
        ]
        for color in test_colors:
            rgb = hex_to_rgb(color)
            result = rgb_to_hex(*rgb)
            assert result == color, f"Failed for {color}"

    def test_rgb_to_hex_to_rgb(self):
        """Test RGB → hex → RGB."""
        test_colors = [
            (255, 0, 0),
            (0, 255, 0),
            (0, 0, 255),
            (255, 255, 255),
            (0, 0, 0),
            (128, 128, 128),
            (255, 170, 187),
            (18, 52, 86),
        ]
        for rgb in test_colors:
            hex_val = rgb_to_hex(*rgb)
            result = hex_to_rgb(hex_val)
            assert result == rgb, f"Failed for {rgb}"


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_three_digit_hex_colors(self):
        # Should fail validation (not 6 characters)
        with pytest.raises(ValueError):
            hex_to_rgb("#FFF")

    def test_rgb_boundary_values(self):
        # Test exact boundaries
        assert rgb_to_hex(0, 0, 0) == "000000"
        assert rgb_to_hex(255, 255, 255) == "FFFFFF"

    def test_rgb_mid_range_values(self):
        # Test mid-range values
        assert rgb_to_hex(127, 127, 127) == "7F7F7F"
        assert rgb_to_hex(128, 128, 128) == "808080"
