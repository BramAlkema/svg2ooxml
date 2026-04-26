"""Unit tests for IR font data structures."""
from __future__ import annotations

from svg2ooxml.ir.fonts import FontFaceRule, FontFaceSrc


class TestFontFaceSrc:
    """Tests for FontFaceSrc dataclass."""

    def test_is_data_uri_true(self):
        """Detect data URI."""
        src = FontFaceSrc(url="data:font/woff2;base64,d09GMgABA...")
        assert src.is_data_uri is True

    def test_is_data_uri_false(self):
        """Non-data URI."""
        src = FontFaceSrc(url="https://example.com/font.woff2")
        assert src.is_data_uri is False

    def test_is_data_uri_case_insensitive(self):
        """Detect data URI regardless of case."""
        src = FontFaceSrc(url="DATA:font/woff2;base64,d09GMgABA...")
        assert src.is_data_uri is True

    def test_is_remote_https(self):
        """Detect HTTPS remote URL."""
        src = FontFaceSrc(url="https://fonts.gstatic.com/font.woff2")
        assert src.is_remote is True

    def test_is_remote_http(self):
        """Detect HTTP remote URL."""
        src = FontFaceSrc(url="http://example.com/font.woff")
        assert src.is_remote is True

    def test_is_remote_case_insensitive(self):
        """Detect mixed-case HTTP(S) URLs."""
        src = FontFaceSrc(url="HTTPS://example.com/font.woff")
        assert src.is_remote is True

    def test_is_remote_false(self):
        """Non-remote URL."""
        src = FontFaceSrc(url="data:font/woff2;base64,abc")
        assert src.is_remote is False

    def test_is_local_with_local_prefix(self):
        """Detect local() font reference."""
        src = FontFaceSrc(url="local(Arial)")
        assert src.is_local is True

    def test_is_local_file_path(self):
        """File path treated as local."""
        src = FontFaceSrc(url="./fonts/custom.ttf")
        assert src.is_local is True

    def test_format_and_tech_optional(self):
        """Format and tech are optional."""
        src = FontFaceSrc(url="font.woff2")
        assert src.format is None
        assert src.tech is None

    def test_format_and_tech_provided(self):
        """Format and tech can be provided."""
        src = FontFaceSrc(url="font.woff2", format="woff2", tech="variations")
        assert src.format == "woff2"
        assert src.tech == "variations"


class TestFontFaceRule:
    """Tests for FontFaceRule dataclass."""

    def test_normalized_family_strips_quotes(self):
        """Normalized family strips quotes."""
        rule = FontFaceRule(
            family="'Roboto'",
            src=[FontFaceSrc(url="roboto.woff2")]
        )
        assert rule.normalized_family == "roboto"

    def test_normalized_family_double_quotes(self):
        """Normalized family strips double quotes."""
        rule = FontFaceRule(
            family='"Open Sans"',
            src=[FontFaceSrc(url="opensans.woff2")]
        )
        assert rule.normalized_family == "open sans"

    def test_normalized_family_no_quotes(self):
        """Normalized family works without quotes."""
        rule = FontFaceRule(
            family="Arial",
            src=[FontFaceSrc(url="arial.ttf")]
        )
        assert rule.normalized_family == "arial"

    def test_weight_numeric_named_bold(self):
        """Named weight 'bold' → 700."""
        rule = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.woff2")],
            weight="bold"
        )
        assert rule.weight_numeric == 700

    def test_weight_numeric_named_normal(self):
        """Named weight 'normal' → 400."""
        rule = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.woff2")],
            weight="normal"
        )
        assert rule.weight_numeric == 400

    def test_weight_numeric_named_light(self):
        """Named weight 'light' → 300."""
        rule = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.woff2")],
            weight="light"
        )
        assert rule.weight_numeric == 300

    def test_weight_numeric_string_400(self):
        """Numeric string '400' → 400."""
        rule = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.woff2")],
            weight="400"
        )
        assert rule.weight_numeric == 400

    def test_weight_numeric_string_700(self):
        """Numeric string '700' → 700."""
        rule = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.woff2")],
            weight="700"
        )
        assert rule.weight_numeric == 700

    def test_weight_numeric_with_whitespace(self):
        """Weight with whitespace '400 ' → 400."""
        rule = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.woff2")],
            weight="400 "
        )
        assert rule.weight_numeric == 400

    def test_weight_numeric_with_leading_whitespace(self):
        """Weight with leading whitespace ' 700' → 700."""
        rule = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.woff2")],
            weight=" 700"
        )
        assert rule.weight_numeric == 700

    def test_weight_numeric_with_decimal(self):
        """Weight with decimal '400.0' → 400."""
        rule = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.woff2")],
            weight="400.0"
        )
        assert rule.weight_numeric == 400

    def test_weight_numeric_invalid_defaults_to_400(self):
        """Invalid weight defaults to 400."""
        rule = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.woff2")],
            weight="invalid"
        )
        assert rule.weight_numeric == 400

    def test_weight_numeric_clamping_below_100(self):
        """Weight below 100 clamped to 100."""
        rule = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.woff2")],
            weight="50"
        )
        assert rule.weight_numeric == 100

    def test_weight_numeric_clamping_above_900(self):
        """Weight above 900 clamped to 900."""
        rule = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.woff2")],
            weight="1000"
        )
        assert rule.weight_numeric == 900

    def test_default_values(self):
        """Default values are correct."""
        rule = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.woff2")]
        )
        assert rule.weight == "normal"
        assert rule.style == "normal"
        assert rule.display == "auto"
        assert rule.unicode_range is None

    def test_all_descriptors_provided(self):
        """All descriptors can be provided."""
        rule = FontFaceRule(
            family="Roboto",
            src=[
                FontFaceSrc(url="roboto.woff2", format="woff2"),
                FontFaceSrc(url="roboto.woff", format="woff"),
            ],
            weight="700",
            style="italic",
            display="swap",
            unicode_range="U+0000-00FF"
        )
        assert rule.family == "Roboto"
        assert len(rule.src) == 2
        assert rule.weight == "700"
        assert rule.style == "italic"
        assert rule.display == "swap"
        assert rule.unicode_range == "U+0000-00FF"
