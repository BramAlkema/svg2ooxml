"""Unit tests for WebFontProvider."""
from __future__ import annotations

import pytest

from svg2ooxml.ir.fonts import FontFaceRule, FontFaceSrc
from svg2ooxml.services.fonts.providers.webfont import WebFontProvider
from svg2ooxml.services.fonts.service import FontQuery


class TestWebFontProvider:
    """Tests for WebFontProvider."""

    def test_resolve_exact_match(self):
        """Exact family, weight, style match."""
        rules = (
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto-400.woff2", format="woff2")],
                weight="400",
                style="normal",
            ),
        )
        provider = WebFontProvider(rules=rules)
        query = FontQuery(family="Roboto", weight=400, style="normal")

        match = provider.resolve(query)

        assert match is not None
        assert match.family == "Roboto"
        assert match.path == "roboto-400.woff2"
        assert match.weight == 400
        assert match.style == "normal"
        assert match.found_via == "webfont"

    def test_resolve_case_insensitive_family(self):
        """Family matching is case-insensitive."""
        rules = (
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto.woff2")],
            ),
        )
        provider = WebFontProvider(rules=rules)

        # Lowercase query
        match = provider.resolve(FontQuery(family="roboto"))
        assert match is not None
        assert match.family == "Roboto"

        # Uppercase query
        match = provider.resolve(FontQuery(family="ROBOTO"))
        assert match is not None

        # Mixed case
        match = provider.resolve(FontQuery(family="RoBoTo"))
        assert match is not None

    def test_resolve_strips_quotes_from_family(self):
        """Family name quotes are stripped."""
        rules = (
            FontFaceRule(
                family="CustomFont",
                src=[FontFaceSrc(url="custom.woff2")],
            ),
        )
        provider = WebFontProvider(rules=rules)

        # Query with double quotes
        match = provider.resolve(FontQuery(family='"CustomFont"'))
        assert match is not None

        # Query with single quotes
        match = provider.resolve(FontQuery(family="'CustomFont'"))
        assert match is not None

    def test_resolve_no_match(self):
        """Return None when no matching family found."""
        rules = (
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto.woff2")],
            ),
        )
        provider = WebFontProvider(rules=rules)

        match = provider.resolve(FontQuery(family="Arial"))
        assert match is None

    def test_resolve_weight_exact_match_preferred(self):
        """Exact weight match is preferred over category match."""
        rules = (
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto-400.woff2")],
                weight="400",
            ),
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto-500.woff2")],
                weight="500",
            ),
        )
        provider = WebFontProvider(rules=rules)

        # Request weight 400 - should get exact match
        match = provider.resolve(FontQuery(family="Roboto", weight=400))
        assert match is not None
        assert "roboto-400" in match.path

        # Request weight 500 - should get exact match
        match = provider.resolve(FontQuery(family="Roboto", weight=500))
        assert match is not None
        assert "roboto-500" in match.path

    def test_resolve_weight_category_fallback(self):
        """Falls back to same weight category if no exact match."""
        rules = (
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto-400.woff2")],
                weight="400",
            ),
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto-700.woff2")],
                weight="700",
            ),
        )
        provider = WebFontProvider(rules=rules)

        # Request 300 (light) - should match 400 (normal category)
        match = provider.resolve(FontQuery(family="Roboto", weight=300))
        assert match is not None
        assert "roboto-400" in match.path

        # Request 800 (extra-bold) - should match 700 (bold category)
        match = provider.resolve(FontQuery(family="Roboto", weight=800))
        assert match is not None
        assert "roboto-700" in match.path

    def test_resolve_style_exact_match_preferred(self):
        """Exact style match is preferred."""
        rules = (
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto-normal.woff2")],
                style="normal",
            ),
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto-italic.woff2")],
                style="italic",
            ),
        )
        provider = WebFontProvider(rules=rules)

        # Request normal
        match = provider.resolve(FontQuery(family="Roboto", style="normal"))
        assert match is not None
        assert "roboto-normal" in match.path

        # Request italic
        match = provider.resolve(FontQuery(family="Roboto", style="italic"))
        assert match is not None
        assert "roboto-italic" in match.path

    def test_resolve_multiple_src_uses_first(self):
        """Uses first src in fallback chain."""
        rules = (
            FontFaceRule(
                family="OpenSans",
                src=[
                    FontFaceSrc(url="opensans.woff2", format="woff2"),
                    FontFaceSrc(url="opensans.woff", format="woff"),
                    FontFaceSrc(url="opensans.ttf", format="truetype"),
                ],
            ),
        )
        provider = WebFontProvider(rules=rules)

        match = provider.resolve(FontQuery(family="OpenSans"))
        assert match is not None
        # Should use first src (highest priority)
        assert match.path == "opensans.woff2"
        assert match.metadata["format"] == "woff2"
        assert match.metadata["src_count"] == 3

    def test_resolve_data_uri_font(self):
        """Data URI fonts are resolved correctly."""
        rules = (
            FontFaceRule(
                family="Custom",
                src=[
                    FontFaceSrc(
                        url="data:font/woff2;base64,d09GMgABAAAAAATcAA0...",
                        format="woff2",
                    )
                ],
            ),
        )
        provider = WebFontProvider(rules=rules)

        match = provider.resolve(FontQuery(family="Custom"))
        assert match is not None
        assert match.path.startswith("data:font/woff2")
        assert match.metadata["is_data_uri"] is True
        assert match.metadata["is_remote"] is False
        assert match.metadata["is_local"] is False
        assert match.embedding_allowed is True

    def test_resolve_remote_font(self):
        """Remote HTTPS fonts are resolved correctly."""
        rules = (
            FontFaceRule(
                family="Roboto",
                src=[
                    FontFaceSrc(
                        url="https://fonts.gstatic.com/s/roboto/v30/font.woff2",
                        format="woff2",
                    )
                ],
            ),
        )
        provider = WebFontProvider(rules=rules)

        match = provider.resolve(FontQuery(family="Roboto"))
        assert match is not None
        assert match.path.startswith("https://")
        assert match.metadata["is_remote"] is True
        assert match.metadata["is_data_uri"] is False
        assert match.metadata["is_local"] is False
        assert match.embedding_allowed is True

    def test_resolve_local_font(self):
        """Local fonts are marked as not embeddable."""
        rules = (
            FontFaceRule(
                family="Roboto",
                src=[
                    FontFaceSrc(url="local(Roboto Regular)"),
                    FontFaceSrc(url="roboto.woff2", format="woff2"),
                ],
            ),
        )
        provider = WebFontProvider(rules=rules)

        match = provider.resolve(FontQuery(family="Roboto"))
        assert match is not None
        # Uses first src (local font)
        assert match.path == "local(Roboto Regular)"
        assert match.metadata["is_local"] is True
        assert match.embedding_allowed is False

    def test_resolve_metadata_preserved(self):
        """Font metadata is preserved in match."""
        rules = (
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto.woff2", format="woff2")],
                display="swap",
                unicode_range="U+0000-00FF",
            ),
        )
        provider = WebFontProvider(rules=rules)

        match = provider.resolve(FontQuery(family="Roboto"))
        assert match is not None
        assert match.metadata["font_display"] == "swap"
        assert match.metadata["unicode_range"] == "U+0000-00FF"

    def test_list_alternatives_returns_all_matches(self):
        """list_alternatives returns all compatible rules."""
        rules = (
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto-400.woff2")],
                weight="400",
            ),
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto-700.woff2")],
                weight="700",
            ),
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto-400-italic.woff2")],
                weight="400",
                style="italic",
            ),
        )
        provider = WebFontProvider(rules=rules)

        matches = list(provider.list_alternatives(FontQuery(family="Roboto", weight=400)))

        # Should return all Roboto variants, sorted by score
        assert len(matches) == 3
        # Best match (400 normal) should be first
        assert matches[0].weight == 400
        assert matches[0].style == "normal"

    def test_list_alternatives_sorted_by_score(self):
        """Alternatives are sorted by compatibility score."""
        rules = (
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto-300.woff2")],
                weight="300",
                style="normal",
            ),
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto-400.woff2")],
                weight="400",
                style="normal",
            ),
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto-700.woff2")],
                weight="700",
                style="normal",
            ),
        )
        provider = WebFontProvider(rules=rules)

        # Request weight 400
        matches = list(provider.list_alternatives(FontQuery(family="Roboto", weight=400)))

        # Exact match (400) should be first
        assert matches[0].weight == 400
        # Compatible category (300) should be second
        assert matches[1].weight == 300
        # Different category (700) should be last
        assert matches[2].weight == 700

    def test_list_alternatives_empty_for_no_match(self):
        """Returns empty list when no family matches."""
        rules = (
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto.woff2")],
            ),
        )
        provider = WebFontProvider(rules=rules)

        matches = list(provider.list_alternatives(FontQuery(family="Arial")))
        assert len(matches) == 0

    def test_scoring_weight_exact_match_highest(self):
        """Exact weight match gets highest score."""
        rule_400 = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test-400.woff2", format="woff2")],
            weight="400",
        )
        rule_700 = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test-700.woff2", format="woff2")],
            weight="700",
        )

        provider = WebFontProvider(rules=(rule_400, rule_700))

        score_400 = provider._score_rule(rule_400, FontQuery(family="Test", weight=400))
        score_700 = provider._score_rule(rule_700, FontQuery(family="Test", weight=400))

        # Exact match should score higher
        assert score_400 > score_700

    def test_scoring_style_exact_match_bonus(self):
        """Exact style match increases score."""
        rule_normal = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test-normal.woff2")],
            style="normal",
        )
        rule_italic = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test-italic.woff2")],
            style="italic",
        )

        provider = WebFontProvider(rules=(rule_normal, rule_italic))

        score_normal = provider._score_rule(
            rule_normal, FontQuery(family="Test", style="normal")
        )
        score_italic = provider._score_rule(
            rule_italic, FontQuery(family="Test", style="normal")
        )

        # Exact style match should score higher
        assert score_normal > score_italic

    def test_scoring_compatible_format_bonus(self):
        """Compatible web formats increase score."""
        rule_woff2 = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.woff2", format="woff2")],
        )
        rule_no_format = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.font")],
        )

        provider = WebFontProvider(rules=(rule_woff2, rule_no_format))

        score_woff2 = provider._score_rule(rule_woff2, FontQuery(family="Test"))
        score_no_format = provider._score_rule(rule_no_format, FontQuery(family="Test"))

        # woff2 should get format bonus
        assert score_woff2 > score_no_format

    def test_index_multiple_rules_same_family(self):
        """Multiple rules with same family are indexed correctly."""
        rules = (
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto-400.woff2")],
                weight="400",
            ),
            FontFaceRule(
                family="Roboto",
                src=[FontFaceSrc(url="roboto-700.woff2")],
                weight="700",
            ),
            FontFaceRule(
                family="OpenSans",
                src=[FontFaceSrc(url="opensans.woff2")],
            ),
        )
        provider = WebFontProvider(rules=rules)

        # Both Roboto rules should be indexed under "roboto"
        assert "roboto" in provider._index
        assert len(provider._index["roboto"]) == 2

        # OpenSans should be separate
        assert "opensans" in provider._index
        assert len(provider._index["opensans"]) == 1

    def test_empty_rules(self):
        """Empty rules tuple returns None for all queries."""
        provider = WebFontProvider(rules=())

        match = provider.resolve(FontQuery(family="Roboto"))
        assert match is None

        matches = list(provider.list_alternatives(FontQuery(family="Roboto")))
        assert len(matches) == 0

    def test_weight_compatibility(self):
        """Weight compatibility check works correctly."""
        provider = WebFontProvider(rules=())

        # Bold category (>=600) is compatible with bold
        assert provider._weight_compatible(700, 600) is True
        assert provider._weight_compatible(600, 700) is True
        assert provider._weight_compatible(800, 700) is True

        # Normal category (<600) is compatible with normal
        assert provider._weight_compatible(400, 300) is True
        assert provider._weight_compatible(300, 500) is True

        # Bold and normal are not compatible
        assert provider._weight_compatible(700, 400) is False
        assert provider._weight_compatible(400, 700) is False

    def test_has_compatible_format(self):
        """Compatible format detection works correctly."""
        provider = WebFontProvider(rules=())

        # woff2 is compatible
        rule_woff2 = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.woff2", format="woff2")],
        )
        assert provider._has_compatible_format(rule_woff2) is True

        # woff is compatible
        rule_woff = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.woff", format="woff")],
        )
        assert provider._has_compatible_format(rule_woff) is True

        # truetype is compatible
        rule_ttf = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="test.ttf", format="truetype")],
        )
        assert provider._has_compatible_format(rule_ttf) is True

        # No format specified (non-local) is compatible
        rule_unknown = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="http://example.com/font.bin")],
        )
        assert provider._has_compatible_format(rule_unknown) is True

        # Local font without format is not compatible
        rule_local = FontFaceRule(
            family="Test",
            src=[FontFaceSrc(url="local(System Font)")],
        )
        assert provider._has_compatible_format(rule_local) is False

    def test_score_components(self):
        """Score components combine correctly."""
        rule = FontFaceRule(
            family="Roboto",
            src=[FontFaceSrc(url="roboto-700-italic.woff2", format="woff2")],
            weight="700",
            style="italic",
        )
        provider = WebFontProvider(rules=(rule,))

        # Perfect match: +0.1 base +1.0 weight +0.5 style +0.3 format = 1.9
        query = FontQuery(family="Roboto", weight=700, style="italic")
        score = provider._score_rule(rule, query)
        assert score == pytest.approx(1.9, abs=0.01)

        # Weight match only: +0.1 base +1.0 weight +0.3 format = 1.4
        query = FontQuery(family="Roboto", weight=700, style="normal")
        score = provider._score_rule(rule, query)
        assert score == pytest.approx(1.4, abs=0.01)

        # No exact matches: +0.1 base +0.3 format = 0.4
        query = FontQuery(family="Roboto", weight=400, style="normal")
        score = provider._score_rule(rule, query)
        assert score == pytest.approx(0.4, abs=0.01)
