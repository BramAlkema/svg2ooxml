"""Font source loading helpers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urldefrag

from svg2ooxml.common.boundaries import (
    classify_resource_href,
    decode_data_uri,
    resolve_local_resource_path,
)

from .loader_types import LoadedFont

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.ir.fonts import FontFaceSrc


logger = logging.getLogger(__name__)


class FontLoaderSourceMixin:
    """Load font bytes from data URIs, remote URLs, and local files."""

    def load_from_src(self, src: FontFaceSrc) -> LoadedFont | None:
        """Load font from a FontFaceSrc."""
        if src.is_data_uri:
            return self.load_data_uri(src.url, format_hint=src.format)
        if src.is_remote and self.allow_network:
            return self.load_remote(src.url, src.format)
        if src.is_local:
            if src.url.startswith("local("):
                self._logger.debug("Skipping local() font reference: %s", src.url)
                return None
            url_no_frag, fragment = urldefrag(src.url)
            resolved = self._resolve_local_path(url_no_frag)
            if resolved is None:
                self._logger.debug("Skipping unresolved local font reference: %s", src.url)
                return None
            return self.load_file(resolved, format_hint=src.format, font_id=fragment)
        self._logger.debug("Unsupported font source: %s", src.url)
        return None

    def load_data_uri(self, data_uri: str, *, format_hint: str | None = None) -> LoadedFont | None:
        """Load font from base64 data URI."""
        data_uri, fragment = urldefrag(data_uri)
        decoded = decode_data_uri(data_uri, max_bytes=self.max_size)
        if decoded is None:
            self._logger.warning("Invalid data URI format")
            return None
        mime_type = decoded.mime_type or "application/octet-stream"
        return self._finalize_loaded_font(
            decoded.data,
            source_url=data_uri[:100] + "..." if len(data_uri) > 100 else data_uri,
            format_hint=format_hint or mime_type,
            font_id=fragment,
        )

    def load_remote(self, url: str, format_hint: str | None = None) -> LoadedFont | None:
        """Load font from remote HTTP(S) URL."""
        if not self.allow_network:
            self._logger.debug("Network requests disabled, skipping remote font: %s", url)
            return None

        if self.fetcher is None:
            self._logger.warning("No FontFetcher available for remote font: %s", url)
            return None

        url_no_frag, fragment = urldefrag(url)
        from .fetcher import normalize_remote_font_url

        if normalize_remote_font_url(url_no_frag) is None:
            self._logger.debug("Skipping unsupported remote font URL: %s", url)
            return None

        from .fetcher import FontSource

        source = FontSource(url=url_no_frag, font_family="unknown")
        try:
            path = self.fetcher.fetch(source)
            if path is None:
                self._logger.warning("Failed to fetch remote font: %s", url)
                return None
            return self._finalize_loaded_font(
                path.read_bytes(),
                source_url=url,
                format_hint=format_hint,
                font_id=fragment,
            )
        except Exception as exc:
            self._logger.warning("Error loading remote font %s: %s", url, exc)
            return None

    def load_file(
        self,
        path: Path,
        *,
        format_hint: str | None = None,
        font_id: str | None = None,
    ) -> LoadedFont | None:
        """Load font from local file path."""
        try:
            if not path.exists():
                self._logger.warning("Font file not found: %s", path)
                return None
            return self._finalize_loaded_font(
                path.read_bytes(),
                source_url=str(path),
                format_hint=format_hint or path.suffix.lstrip("."),
                font_id=font_id,
            )
        except Exception as exc:
            self._logger.warning("Error loading font file %s: %s", path, exc)
            return None

    def _resolve_local_path(self, url: str) -> Path | None:
        token = self._normalize_local_font_url(url)
        if not token or self.base_dir is None:
            return None
        root = self.asset_root or self.base_dir
        return resolve_local_resource_path(token, self.base_dir, asset_root=root)

    @staticmethod
    def _normalize_local_font_url(url: str) -> str | None:
        reference = classify_resource_href(url)
        if reference is None or reference.kind != "local-path":
            return None
        token = reference.path or reference.normalized
        if token.lower().startswith("local("):
            return None
        return token


__all__ = ["FontLoaderSourceMixin"]
