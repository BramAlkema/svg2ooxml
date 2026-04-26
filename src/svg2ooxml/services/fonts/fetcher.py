"""Remote font fetching utilities."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

MAX_FONT_SIZE = 10 * 1024 * 1024  # 10 MiB safety limit
ENV_FONT_CACHE_DIR = "SVG2OOXML_FONT_CACHE_DIR"
ENV_WEB_FONT_CACHE_DIR = "SVG2OOXML_WEB_FONT_CACHE"
FONT_EXTENSIONS = {".ttf", ".otf", ".woff", ".woff2", ".svg", ".eot"}
GOOGLE_FONTS_CSS_HOST = "fonts.googleapis.com"


def _default_cache_directory() -> Path:
    override = os.getenv(ENV_FONT_CACHE_DIR) or os.getenv(ENV_WEB_FONT_CACHE_DIR)
    if override:
        return Path(override).expanduser()
    xdg_cache = os.getenv("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache).expanduser() / "svg2ooxml" / "fonts"
    return Path.home() / ".cache" / "svg2ooxml" / "fonts"


@dataclass(frozen=True)
class FontSource:
    """Describe a remote font resource."""

    url: str
    font_family: str
    font_weight: str = "regular"
    font_style: str = "normal"


class FontFetcher:
    """Download and cache remote font files for embedding."""

    def __init__(
        self,
        cache_directory: str | Path | None = None,
        *,
        allow_network: bool = True,
        max_download_size: int = MAX_FONT_SIZE,
    ) -> None:
        self.cache_directory = Path(cache_directory or _default_cache_directory())
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        self.allow_network = allow_network
        self.max_download_size = max_download_size

    def fetch_sources(self, sources: Iterable[FontSource]) -> list[tuple[FontSource, Path]]:
        results: list[tuple[FontSource, Path]] = []
        for source in sources:
            path = self.fetch(source)
            if path is not None:
                results.append((source, path))
        return results

    def fetch(self, source: FontSource) -> Path | None:
        url = normalize_remote_font_url(source.url)
        if url is None:
            return None

        cache_key = self._cache_key(url)
        target_path = self.cache_directory / cache_key
        if target_path.exists():
            try:
                if target_path.stat().st_size > 0:
                    return target_path
                target_path.unlink(missing_ok=True)
            except Exception:
                return target_path

        if not self.allow_network:
            return None

        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        try:
            if _is_google_fonts_css_host(host):
                css_bytes = self._download_bytes(url)
                if css_bytes is None:
                    return None
                for font_url in self._extract_urls_from_css(css_bytes.decode("utf-8", errors="ignore")):
                    path = self._download_to_cache(font_url)
                    if path is not None:
                        return path
                return None
            return self._download_to_cache(url)
        except Exception:
            if target_path.exists():
                target_path.unlink(missing_ok=True)
            return None

    def _download_to_cache(self, url: str) -> Path | None:
        url = normalize_remote_font_url(url)
        if url is None:
            return None
        cache_key = self._cache_key(url)
        target_path = self.cache_directory / cache_key
        data = self._download_bytes(url)
        if data is None or not self._sanitize_font_data(data):
            return None
        tmp_path: Path | None = None
        try:
            self.cache_directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.cache_directory, delete=False) as tmp_file:
                tmp_file.write(data)
                tmp_path = Path(tmp_file.name)
            tmp_path.replace(target_path)
            return target_path
        except Exception:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
            return None

    def _download_bytes(self, url: str) -> bytes | None:
        normalized_url = normalize_remote_font_url(url)
        if normalized_url is None:
            return None
        try:
            with urllib.request.urlopen(normalized_url, timeout=15) as response:
                final_url = getattr(response, "geturl", lambda: normalized_url)()
                if normalize_remote_font_url(final_url) is None:
                    return None
                data = response.read(self.max_download_size + 1)
        except Exception:
            return None
        if len(data) > self.max_download_size:
            return None
        return data

    @staticmethod
    def _sanitize_font_data(data: bytes) -> bool:
        sniff = data[:512].lower()
        if b"<script" in sniff or b"<html" in sniff:
            return False
        return True

    @staticmethod
    def _extract_urls_from_css(css: str) -> list[str]:
        urls: list[str] = []
        for match in re.findall(r"url\(\s*['\"]?(.*?)['\"]?\s*\)", css, flags=re.IGNORECASE):
            url = normalize_remote_font_url(match.strip())
            if url is not None:
                urls.append(url)
        return urls

    @staticmethod
    def _cache_key(url: str) -> str:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        parsed = urlparse(url)
        _, ext = os.path.splitext(parsed.path)
        ext = ext.lower() if ext.lower() in FONT_EXTENSIONS else ".ttf"
        return f"{digest}{ext}"


def normalize_remote_font_url(url: str | None) -> str | None:
    if not isinstance(url, str):
        return None
    token = url.strip()
    if not token:
        return None
    parsed = urlparse(token)
    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if not parsed.hostname:
        return None
    return token


def _is_google_fonts_css_host(host: str) -> bool:
    return host == GOOGLE_FONTS_CSS_HOST


__all__ = [
    "FontFetcher",
    "FontSource",
    "MAX_FONT_SIZE",
    "normalize_remote_font_url",
]
