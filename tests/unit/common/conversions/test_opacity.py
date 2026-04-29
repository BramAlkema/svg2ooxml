"""Tests for opacity/alpha conversion utilities."""


from svg2ooxml.common.conversions.opacity import (
    PPT_OPACITY_SCALE,
    alpha_to_ppt,
    opacity_to_ppt,
    parse_authored_opacity,
    parse_opacity,
    percentage_to_ppt,
    ppt_to_alpha,
    ppt_to_opacity,
    ppt_to_percentage,
)


class TestOpacityToPPT:
    """Test opacity_to_ppt conversion."""

    def test_fully_transparent(self):
        assert opacity_to_ppt(0.0) == 0

    def test_fully_opaque(self):
        assert opacity_to_ppt(1.0) == 100000

    def test_half_opaque(self):
        assert opacity_to_ppt(0.5) == 50000

    def test_various_values(self):
        assert opacity_to_ppt(0.25) == 25000
        assert opacity_to_ppt(0.75) == 75000
        assert opacity_to_ppt(0.7) == 70000

    def test_clamping_above_one(self):
        assert opacity_to_ppt(1.5) == 100000
        assert opacity_to_ppt(2.0) == 100000
        assert opacity_to_ppt(10.0) == 100000

    def test_clamping_below_zero(self):
        assert opacity_to_ppt(-0.5) == 0
        assert opacity_to_ppt(-1.0) == 0
        assert opacity_to_ppt(-10.0) == 0


class TestPPTToOpacity:
    """Test ppt_to_opacity conversion."""

    def test_zero(self):
        assert ppt_to_opacity(0) == 0.0

    def test_fully_opaque(self):
        assert ppt_to_opacity(100000) == 1.0

    def test_half_opaque(self):
        assert ppt_to_opacity(50000) == 0.5

    def test_various_values(self):
        assert ppt_to_opacity(25000) == 0.25
        assert ppt_to_opacity(75000) == 0.75
        assert ppt_to_opacity(70000) == 0.7

    def test_clamping_above_scale(self):
        assert ppt_to_opacity(150000) == 1.0
        assert ppt_to_opacity(200000) == 1.0

    def test_clamping_below_zero(self):
        assert ppt_to_opacity(-50000) == 0.0


class TestParseOpacity:
    """Test CSS/SVG opacity parsing."""

    def test_number(self):
        assert parse_opacity("0.5") == 0.5

    def test_percentage(self):
        assert parse_opacity("50%") == 0.5

    def test_calc_number_and_percentage(self):
        assert parse_opacity("calc(0.25 + 0.25)") == 0.5
        assert parse_opacity("calc(25% + 25%)") == 0.5

    def test_clamps_numeric_values(self):
        assert parse_opacity("50") == 1.0
        assert parse_opacity("-2") == 0.0

    def test_invalid_uses_default(self):
        assert parse_opacity("bad", default=0.25) == 0.25
        assert parse_opacity("calc(1px + 2px)", default=0.25) == 0.25


class TestParseAuthoredOpacity:
    """Test animation-authored opacity parsing."""

    def test_number_and_percent_scales(self):
        assert parse_authored_opacity("0.5") == 0.5
        assert parse_authored_opacity("50") == 0.5
        assert parse_authored_opacity("50%") == 0.5

    def test_calc_number_and_percentage(self):
        assert parse_authored_opacity("calc(25 + 25)") == 0.5
        assert parse_authored_opacity("calc(25% + 25%)") == 0.5


class TestAlphaToPPT:
    """Test alpha_to_ppt (should be same as opacity_to_ppt)."""

    def test_alias_behavior(self):
        assert alpha_to_ppt(1.0) == opacity_to_ppt(1.0)
        assert alpha_to_ppt(0.5) == opacity_to_ppt(0.5)
        assert alpha_to_ppt(0.0) == opacity_to_ppt(0.0)


class TestPPTToAlpha:
    """Test ppt_to_alpha (should be same as ppt_to_opacity)."""

    def test_alias_behavior(self):
        assert ppt_to_alpha(100000) == ppt_to_opacity(100000)
        assert ppt_to_alpha(50000) == ppt_to_opacity(50000)
        assert ppt_to_alpha(0) == ppt_to_opacity(0)


class TestPercentageToPPT:
    """Test percentage_to_ppt conversion."""

    def test_zero_percent(self):
        assert percentage_to_ppt(0.0) == 0

    def test_hundred_percent(self):
        assert percentage_to_ppt(100.0) == 100000

    def test_fifty_percent(self):
        assert percentage_to_ppt(50.0) == 50000

    def test_various_values(self):
        assert percentage_to_ppt(25.0) == 25000
        assert percentage_to_ppt(75.0) == 75000
        assert percentage_to_ppt(70.0) == 70000


class TestPPTToPercentage:
    """Test ppt_to_percentage conversion."""

    def test_zero(self):
        assert ppt_to_percentage(0) == 0.0

    def test_fully_opaque(self):
        assert ppt_to_percentage(100000) == 100.0

    def test_half(self):
        assert ppt_to_percentage(50000) == 50.0

    def test_various_values(self):
        assert ppt_to_percentage(25000) == 25.0
        assert ppt_to_percentage(75000) == 75.0


class TestRoundtrip:
    """Test roundtrip conversions."""

    def test_opacity_roundtrip(self):
        """Test opacity → ppt → opacity."""
        for opacity in [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]:
            ppt = opacity_to_ppt(opacity)
            result = ppt_to_opacity(ppt)
            assert abs(result - opacity) < 0.00001, f"Failed for {opacity}"

    def test_percentage_roundtrip(self):
        """Test percentage → ppt → percentage."""
        for percentage in [0.0, 10.0, 25.0, 50.0, 75.0, 90.0, 100.0]:
            ppt = percentage_to_ppt(percentage)
            result = ppt_to_percentage(ppt)
            assert abs(result - percentage) < 0.001, f"Failed for {percentage}%"


class TestConstants:
    """Test module constants."""

    def test_ppt_opacity_scale(self):
        assert PPT_OPACITY_SCALE == 100000
