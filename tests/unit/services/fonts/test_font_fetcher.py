from __future__ import annotations

from svg2ooxml.services.fonts.fetcher import (
    FontFetcher,
    FontSource,
    normalize_remote_font_url,
)


def test_normalize_remote_font_url_rejects_non_http_schemes() -> None:
    assert normalize_remote_font_url("file:///tmp/font.woff2") is None
    assert normalize_remote_font_url("ftp://example.com/font.woff2") is None
    assert normalize_remote_font_url("data:font/woff2;base64,AA==") is None


def test_normalize_remote_font_url_rejects_private_network_hosts() -> None:
    assert normalize_remote_font_url("http://localhost/font.woff2") is None
    assert normalize_remote_font_url("http://127.0.0.1/font.woff2") is None
    assert normalize_remote_font_url("http://169.254.169.254/font.woff2") is None


def test_fetch_rejects_non_http_source_without_network(tmp_path) -> None:
    source = FontSource(url="file:///tmp/font.woff2", font_family="Bad")
    fetcher = FontFetcher(cache_directory=tmp_path, allow_network=True)

    assert fetcher.fetch(source) is None


def test_extract_urls_from_css_filters_non_remote_urls() -> None:
    css = """
    @font-face {
      src: url('file:///tmp/font.woff2'),
           url('https://example.com/font.woff2'),
           url(data:font/woff2;base64,AA==);
    }
    """

    assert FontFetcher._extract_urls_from_css(css) == ["https://example.com/font.woff2"]


def test_cache_key_uses_url_path_extension_without_query() -> None:
    key = FontFetcher._cache_key("https://example.com/font.woff2?v=123")

    assert key.endswith(".woff2")


def test_cache_key_defaults_unknown_extension_to_ttf() -> None:
    key = FontFetcher._cache_key("https://example.com/download?family=Roboto")

    assert key.endswith(".ttf")
