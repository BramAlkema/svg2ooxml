"""Integration tests for WebFontProvider with FontLoader.

Tests the complete flow: FontFaceRule -> WebFontProvider -> FontLoader -> LoadedFont
"""
from __future__ import annotations

import base64
from pathlib import Path

from svg2ooxml.ir.fonts import FontFaceRule, FontFaceSrc
from svg2ooxml.services.fonts.loader import FontLoader
from svg2ooxml.services.fonts.providers.webfont import WebFontProvider
from svg2ooxml.services.fonts.service import FontQuery


class TestWebFontLoadingIntegration:
    """Integration tests for WebFontProvider with FontLoader."""

    def test_load_ttf_data_uri_end_to_end(self):
        """End-to-end: Load TTF from data URI through provider."""
        # Create minimal TTF font
        ttf_data = b"\x00\x01\x00\x00" + b"\x00" * 100
        b64_data = base64.b64encode(ttf_data).decode("ascii")
        data_uri = f"data:font/ttf;base64,{b64_data}"

        # Create @font-face rule
        rule = FontFaceRule(
            family="TestFont",
            src=[FontFaceSrc(url=data_uri, format="ttf")],
            weight="400",
            style="normal",
        )

        # Create provider with loader
        loader = FontLoader()
        provider = WebFontProvider(
            rules=(rule,),
            loader=loader,
            enable_loading=True,
            cache_loaded_fonts=True,
        )

        # Query for font
        query = FontQuery(family="TestFont", weight=400, style="normal")
        match = provider.resolve(query)

        # Verify match
        assert match is not None
        assert match.family == "TestFont"
        assert match.weight == 400
        assert match.style == "normal"

        # Verify font was loaded
        assert match.metadata["loaded"] is True
        assert match.metadata["font_data"] == ttf_data
        assert match.metadata["loaded_format"] == "ttf"
        assert match.metadata["loaded_size_bytes"] == len(ttf_data)
        assert match.metadata["decompressed"] is False

    def test_load_woff_data_uri_end_to_end(self, tmp_path: Path):
        """End-to-end: Load and decompress WOFF from data URI."""
        # Create a minimal WOFF (this will fail decompression but test the flow)
        woff_data = b"wOFF" + b"\x00" * 100
        b64_data = base64.b64encode(woff_data).decode("ascii")
        data_uri = f"data:font/woff;base64,{b64_data}"

        rule = FontFaceRule(
            family="WoffFont",
            src=[FontFaceSrc(url=data_uri, format="woff")],
            weight="400",
            style="normal",
        )

        loader = FontLoader()
        provider = WebFontProvider(
            rules=(rule,),
            loader=loader,
            enable_loading=True,
        )

        query = FontQuery(family="WoffFont", weight=400, style="normal")
        match = provider.resolve(query)

        # Even if decompression fails, provider should return match
        # (loader returns None on decompression failure, so loaded=False)
        assert match is not None
        assert match.metadata["loaded"] is False  # Decompression failed

    def test_fallback_src_chain_loading(self):
        """Test loading tries each src in order until success."""
        ttf_data = b"\x00\x01\x00\x00" + b"\x00" * 100
        b64_data = base64.b64encode(ttf_data).decode("ascii")
        valid_uri = f"data:font/ttf;base64,{b64_data}"

        # Create rule with multiple src (first invalid, second valid)
        rule = FontFaceRule(
            family="FallbackFont",
            src=[
                FontFaceSrc(url="local(Arial)", format=None),  # Will be skipped
                FontFaceSrc(url=valid_uri, format="ttf"),  # Should succeed
            ],
            weight="400",
            style="normal",
        )

        loader = FontLoader()
        provider = WebFontProvider(rules=(rule,), loader=loader, enable_loading=True)

        query = FontQuery(family="FallbackFont", weight=400, style="normal")
        match = provider.resolve(query)

        # Should load from second src
        assert match is not None
        assert match.metadata["loaded"] is True
        assert match.metadata["font_data"] == ttf_data

    def test_font_caching_across_queries(self):
        """Test that loaded fonts are cached and reused."""
        ttf_data = b"\x00\x01\x00\x00" + b"\x00" * 100
        b64_data = base64.b64encode(ttf_data).decode("ascii")
        data_uri = f"data:font/ttf;base64,{b64_data}"

        rule = FontFaceRule(
            family="CachedFont",
            src=[FontFaceSrc(url=data_uri, format="ttf")],
            weight="400",
            style="normal",
        )

        loader = FontLoader()
        provider = WebFontProvider(
            rules=(rule,),
            loader=loader,
            enable_loading=True,
            cache_loaded_fonts=True,
        )

        # First query - loads font
        query1 = FontQuery(family="CachedFont", weight=400, style="normal")
        match1 = provider.resolve(query1)
        assert match1 is not None
        assert match1.metadata["loaded"] is True

        # Check cache stats
        stats = provider.get_cache_stats()
        assert stats["cached_fonts"] == 1
        assert stats["total_bytes"] == len(ttf_data)

        # Second query - should use cache
        query2 = FontQuery(family="CachedFont", weight=400, style="normal")
        match2 = provider.resolve(query2)
        assert match2 is not None
        assert match2.metadata["loaded"] is True
        assert match2.metadata["font_data"] == ttf_data

        # Cache stats unchanged (same font)
        stats = provider.get_cache_stats()
        assert stats["cached_fonts"] == 1

        # Clear cache
        provider.clear_cache()
        stats = provider.get_cache_stats()
        assert stats["cached_fonts"] == 0
        assert stats["total_bytes"] == 0

    def test_loading_disabled_no_font_data(self):
        """Test that with loading disabled, no font data is loaded."""
        ttf_data = b"\x00\x01\x00\x00" + b"\x00" * 100
        b64_data = base64.b64encode(ttf_data).decode("ascii")
        data_uri = f"data:font/ttf;base64,{b64_data}"

        rule = FontFaceRule(
            family="NoLoadFont",
            src=[FontFaceSrc(url=data_uri, format="ttf")],
            weight="400",
            style="normal",
        )

        loader = FontLoader()
        provider = WebFontProvider(
            rules=(rule,),
            loader=loader,
            enable_loading=False,  # Disabled
        )

        query = FontQuery(family="NoLoadFont", weight=400, style="normal")
        match = provider.resolve(query)

        # Match found but font not loaded
        assert match is not None
        assert match.metadata["loaded"] is False
        assert "font_data" not in match.metadata

    def test_no_loader_provided_no_loading(self):
        """Test that without a loader, fonts are not loaded."""
        ttf_data = b"\x00\x01\x00\x00" + b"\x00" * 100
        b64_data = base64.b64encode(ttf_data).decode("ascii")
        data_uri = f"data:font/ttf;base64,{b64_data}"

        rule = FontFaceRule(
            family="NoLoaderFont",
            src=[FontFaceSrc(url=data_uri, format="ttf")],
            weight="400",
            style="normal",
        )

        # No loader provided
        provider = WebFontProvider(
            rules=(rule,),
            loader=None,
            enable_loading=True,
        )

        query = FontQuery(family="NoLoaderFont", weight=400, style="normal")
        match = provider.resolve(query)

        # Match found but font not loaded
        assert match is not None
        assert match.metadata["loaded"] is False

    def test_multiple_fonts_different_weights_cached_separately(self):
        """Test that different weights of same family are cached separately."""
        # Create two TTF fonts
        ttf_400 = b"\x00\x01\x00\x00" + b"A" * 100
        ttf_700 = b"\x00\x01\x00\x00" + b"B" * 100

        b64_400 = base64.b64encode(ttf_400).decode("ascii")
        b64_700 = base64.b64encode(ttf_700).decode("ascii")

        uri_400 = f"data:font/ttf;base64,{b64_400}"
        uri_700 = f"data:font/ttf;base64,{b64_700}"

        # Create two rules for different weights
        rule_400 = FontFaceRule(
            family="MultiWeight",
            src=[FontFaceSrc(url=uri_400, format="ttf")],
            weight="400",
            style="normal",
        )
        rule_700 = FontFaceRule(
            family="MultiWeight",
            src=[FontFaceSrc(url=uri_700, format="ttf")],
            weight="700",
            style="normal",
        )

        loader = FontLoader()
        provider = WebFontProvider(
            rules=(rule_400, rule_700),
            loader=loader,
            enable_loading=True,
            cache_loaded_fonts=True,
        )

        # Load both fonts
        match_400 = provider.resolve(FontQuery(family="MultiWeight", weight=400, style="normal"))
        match_700 = provider.resolve(FontQuery(family="MultiWeight", weight=700, style="normal"))

        # Both loaded
        assert match_400 is not None
        assert match_400.metadata["loaded"] is True
        assert match_400.metadata["font_data"] == ttf_400

        assert match_700 is not None
        assert match_700.metadata["loaded"] is True
        assert match_700.metadata["font_data"] == ttf_700

        # Both cached separately
        stats = provider.get_cache_stats()
        assert stats["cached_fonts"] == 2
        assert stats["total_bytes"] == len(ttf_400) + len(ttf_700)

    def test_list_alternatives_includes_loaded_data(self):
        """Test that list_alternatives also includes loaded font data."""
        ttf_400 = b"\x00\x01\x00\x00" + b"A" * 100
        ttf_700 = b"\x00\x01\x00\x00" + b"B" * 100

        b64_400 = base64.b64encode(ttf_400).decode("ascii")
        b64_700 = base64.b64encode(ttf_700).decode("ascii")

        uri_400 = f"data:font/ttf;base64,{b64_400}"
        uri_700 = f"data:font/ttf;base64,{b64_700}"

        rule_400 = FontFaceRule(
            family="AltFont",
            src=[FontFaceSrc(url=uri_400, format="ttf")],
            weight="400",
            style="normal",
        )
        rule_700 = FontFaceRule(
            family="AltFont",
            src=[FontFaceSrc(url=uri_700, format="ttf")],
            weight="700",
            style="normal",
        )

        loader = FontLoader()
        provider = WebFontProvider(
            rules=(rule_400, rule_700),
            loader=loader,
            enable_loading=True,
        )

        # List alternatives
        query = FontQuery(family="AltFont", weight=400, style="normal")
        alternatives = list(provider.list_alternatives(query))

        # Both alternatives loaded
        assert len(alternatives) == 2
        assert all(alt.metadata["loaded"] for alt in alternatives)
        assert alternatives[0].metadata["font_data"] in (ttf_400, ttf_700)
        assert alternatives[1].metadata["font_data"] in (ttf_400, ttf_700)
