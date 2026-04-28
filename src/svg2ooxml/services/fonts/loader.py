"""Font loading and decompression for web fonts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from svg2ooxml.services.fonts.fontforge_utils import FONTFORGE_AVAILABLE

from .loader_processing import FontLoaderProcessingMixin
from .loader_sources import FontLoaderSourceMixin
from .loader_types import LoadedFont, WOFFTableEntry
from .loader_woff import decompress_woff, decompress_woff2

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from svg2ooxml.services.fonts.fetcher import FontFetcher

logger = logging.getLogger(__name__)

MAX_FONT_SIZE = 10 * 1024 * 1024  # 10 MiB safety limit


class FontLoader(FontLoaderSourceMixin, FontLoaderProcessingMixin):
    """Load and decompress fonts from various sources."""

    def __init__(
        self,
        fetcher: FontFetcher | None = None,
        *,
        allow_network: bool = True,
        max_size: int = MAX_FONT_SIZE,
        base_dir: Path | str | None = None,
        asset_root: Path | str | None = None,
        allow_svg_fonts: bool = True,
        logger: logging.Logger | None = None,
    ) -> None:
        """Initialize font loader."""
        self.fetcher = fetcher
        self.allow_network = allow_network
        self.max_size = max_size
        self.base_dir = Path(base_dir).expanduser().resolve() if base_dir is not None else None
        self.asset_root = (
            Path(asset_root).expanduser().resolve()
            if asset_root is not None
            else self.base_dir
        )
        self.allow_svg_fonts = allow_svg_fonts
        self._logger = logger or globals()["logger"]

    def _decompress_woff2(self, data: bytes) -> bytes | None:
        return decompress_woff2(
            data,
            max_size=self.max_size,
            fontforge_available=FONTFORGE_AVAILABLE,
            logger=self._logger,
        )

    def _decompress_woff(self, data: bytes) -> bytes | None:
        return decompress_woff(data, max_size=self.max_size, logger=self._logger)


__all__ = [
    "FontLoader",
    "LoadedFont",
    "MAX_FONT_SIZE",
    "FONTFORGE_AVAILABLE",
    "WOFFTableEntry",
]
