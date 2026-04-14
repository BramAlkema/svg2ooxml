"""Unit tests for paint module color parsing."""


from svg2ooxml.core.resvg.painting.paint import (
    _parse_component,
    parse_color,
    resolve_stroke,
)


class TestParseComponent:
    """Test suite for _parse_component helper function."""

    def test_parse_absolute_zero(self):
        """Test parsing absolute value 0."""
        assert _parse_component("0") == 0

    def test_parse_absolute_255(self):
        """Test parsing absolute value 255."""
        assert _parse_component("255") == 255

    def test_parse_absolute_128(self):
        """Test parsing absolute value 128."""
        assert _parse_component("128") == 128

    def test_parse_percentage_zero(self):
        """Test parsing 0%."""
        assert _parse_component("0%") == 0

    def test_parse_percentage_hundred(self):
        """Test parsing 100%."""
        assert _parse_component("100%") == 255

    def test_parse_percentage_fifty(self):
        """Test parsing 50%."""
        # 50% = 0.5 * 255 = 127.5, rounds to 128
        assert _parse_component("50%") == 128

    def test_parse_percentage_rounding_up(self):
        """Test that percentage values round up correctly.

        This test verifies the fix for rounding fidelity:
        99.9% should become 255, not 254.
        """
        # 99.9% = 0.999 * 255 = 254.745, rounds to 255
        assert _parse_component("99.9%") == 255

    def test_parse_percentage_rounding_down(self):
        """Test that percentage values round down correctly."""
        # 99.6% = 0.996 * 255 = 253.98, rounds to 254
        assert _parse_component("99.6%") == 254

    def test_parse_percentage_25(self):
        """Test parsing 25%."""
        # 25% = 0.25 * 255 = 63.75, rounds to 64
        assert _parse_component("25%") == 64

    def test_parse_percentage_75(self):
        """Test parsing 75%."""
        # 75% = 0.75 * 255 = 191.25, rounds to 191
        assert _parse_component("75%") == 191

    def test_parse_with_whitespace(self):
        """Test that whitespace is properly stripped."""
        assert _parse_component("  128  ") == 128
        assert _parse_component("  50%  ") == 128

    def test_parse_invalid_returns_none(self):
        """Test that invalid input returns None."""
        assert _parse_component("invalid") is None
        assert _parse_component("abc%") is None
        assert _parse_component("") is None

    def test_parse_percentage_clamping(self):
        """Test that percentages are clamped to 0-100%.

        The _clamp function ensures values stay in 0.0-1.0 range
        before multiplying by 255.
        """
        # Over 100% gets clamped to 100% → 255
        assert _parse_component("150%") == 255
        # Negative gets clamped to 0% → 0
        assert _parse_component("-10%") == 0


class TestParseColor:
    """Test suite for parse_color function."""

    def test_parse_hex_color_red(self):
        """Test parsing red #FF0000."""
        color = parse_color("#FF0000", 1.0)
        assert color is not None
        assert color.r == 1.0
        assert color.g == 0.0
        assert color.b == 0.0
        assert color.a == 1.0

    def test_parse_hex_color_green(self):
        """Test parsing green #00FF00."""
        color = parse_color("#00FF00", 1.0)
        assert color is not None
        assert color.r == 0.0
        assert color.g == 1.0
        assert color.b == 0.0

    def test_parse_hex_color_blue(self):
        """Test parsing blue #0000FF."""
        color = parse_color("#0000FF", 1.0)
        assert color is not None
        assert color.r == 0.0
        assert color.g == 0.0
        assert color.b == 1.0

    def test_parse_hex_short_form(self):
        """Test parsing short form hex #FFF."""
        color = parse_color("#FFF", 1.0)
        assert color is not None
        assert color.r == 1.0
        assert color.g == 1.0
        assert color.b == 1.0

    def test_parse_rgb_function(self):
        """Test parsing rgb(255, 128, 0)."""
        color = parse_color("rgb(255, 128, 0)", 1.0)
        assert color is not None
        assert color.r == 1.0
        # 128 / 255 = 0.5019...
        assert abs(color.g - 128/255) < 0.001
        assert color.b == 0.0

    def test_parse_rgb_function_with_percentages(self):
        """Test parsing rgb(100%, 50%, 0%) with rounding."""
        color = parse_color("rgb(100%, 50%, 0%)", 1.0)
        assert color is not None
        assert color.r == 1.0
        # 50% should parse to 128 (with rounding), then 128/255
        assert abs(color.g - 128/255) < 0.001
        assert color.b == 0.0

    def test_parse_rgb_function_rounding_fidelity(self):
        """Test that rgb() percentages use proper rounding.

        This verifies the fix: rgb(99.9%, ...) should round to 255, not 254.
        """
        color = parse_color("rgb(99.9%, 0%, 0%)", 1.0)
        assert color is not None
        # 99.9% → 255 (with round) → 255/255 = 1.0
        assert color.r == 1.0

    def test_parse_with_opacity(self):
        """Test that opacity is properly applied."""
        color = parse_color("#FFFFFF", 0.5)
        assert color is not None
        assert color.a == 0.5

    def test_parse_none_returns_none(self):
        """Test that None input returns None."""
        assert parse_color(None, 1.0) is None

    def test_parse_invalid_returns_none(self):
        """Test that invalid color strings return None."""
        assert parse_color("invalid", 1.0) is None
        assert parse_color("rgb(invalid)", 1.0) is None


class TestResolveStroke:
    """Test suite for stroke defaulting behavior."""

    def test_defaults_stroke_width_to_one_for_stroked_shapes(self):
        stroke = resolve_stroke("green", None, None, None)
        assert stroke.color is not None
        assert stroke.width == 1.0


__all__ = ["TestParseComponent", "TestParseColor"]
