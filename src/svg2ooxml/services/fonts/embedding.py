"""Font embedding engine with basic subsetting support."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import replace

from svg2ooxml.services.fonts.embedding_conversion import (
    ensure_truetype_outlines as _ensure_truetype_outlines,
)
from svg2ooxml.services.fonts.embedding_fontforge import FontForgeSubsetMixin
from svg2ooxml.services.fonts.embedding_payload import FontEmbeddingPayloadMixin
from svg2ooxml.services.fonts.embedding_permissions import (
    FontEmbeddingPermissionMixin,
    coerce_embedding_permission,
)
from svg2ooxml.services.fonts.embedding_subsets import FontEmbeddingSubsetMixin
from svg2ooxml.services.fonts.embedding_text import FontEmbeddingTextMixin
from svg2ooxml.services.fonts.embedding_types import (
    EmbeddedFontPayload,
    EmbeddingPermission,
    FontEmbeddingRequest,
    FontEmbeddingResult,
    FontOptimisationLevel,
)
from svg2ooxml.services.fonts.fontforge_utils import FONTFORGE_AVAILABLE

logger = logging.getLogger(__name__)


class FontEmbeddingEngine(
    FontEmbeddingTextMixin,
    FontEmbeddingPermissionMixin,
    FontEmbeddingPayloadMixin,
    FontForgeSubsetMixin,
    FontEmbeddingSubsetMixin,
):
    """Subset fonts using FontForge when available and track simple stats."""

    def __init__(self) -> None:
        self._stats: dict[str, int] = {
            "subset_requests": 0,
            "subset_success": 0,
            "subset_failures": 0,
            "subset_cache_hits": 0,
            "bytes_total": 0,
            "packaged_fonts": 0,
            "packaged_bytes": 0,
            "permission_denied": 0,
            "bitmap_only": 0,
        }
        self._cache: dict[str, FontEmbeddingResult] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def can_embed(self, font_path: str) -> bool:
        """Return whether the font can be embedded (basic fsType inspection)."""

        permission = coerce_embedding_permission(
            self._read_embedding_permission(font_path)
        )
        return permission not in {
            EmbeddingPermission.RESTRICTED,
            EmbeddingPermission.UNKNOWN,
        }

    def subset_font(self, request: FontEmbeddingRequest) -> FontEmbeddingResult | None:
        """Produce (or reuse) a subsetted font for the given glyph set."""

        self._stats["subset_requests"] += 1
        cache_key = self._cache_key(request)
        if cache_key in self._cache:
            self._stats["subset_cache_hits"] += 1
            return self._cache[cache_key]

        text_payload = self._prepare_subset_text(request)
        if not text_payload:
            logger.debug("No glyphs or characters provided for embedding; skipping subset generation.")
            self._stats["subset_failures"] += 1
            return None

        font_data = None
        if isinstance(request.metadata, Mapping):
            data = request.metadata.get("font_data")
            if isinstance(data, (bytes, bytearray)):
                font_data = bytes(data)
        permission = coerce_embedding_permission(
            self._read_embedding_permission(request.font_path, font_data)
        )
        if permission == EmbeddingPermission.RESTRICTED:
            logger.info("Font %s prohibits embedding (fsType restricted)", request.font_path)
            self._stats["permission_denied"] += 1
            self._stats["subset_failures"] += 1
            return None
        if permission == EmbeddingPermission.BITMAP_ONLY:
            self._stats["bitmap_only"] += 1

        strategy = (request.subset_strategy or "glyph").lower()
        if permission == EmbeddingPermission.NO_SUBSETTING and strategy != "none":
            logger.debug("Font %s forbids subsetting; switching to copy", request.font_path)
            strategy = "none"
        if permission == EmbeddingPermission.BITMAP_ONLY and strategy != "none":
            logger.debug("Font %s allows bitmap-only embedding; switching to copy", request.font_path)
            strategy = "none"

        effective_request = request
        if strategy != "none" and not FONTFORGE_AVAILABLE:
            logger.debug("FontForge not available; falling back to direct embedding for %s", request.font_path)
            strategy = "none"
            effective_request = replace(request, subset_strategy="none")

        if strategy == "none":
            result = self._subset_copy(effective_request, permission)
        else:
            result = self._subset_with_fontforge(effective_request, text_payload, permission)

        if result is None:
            self._stats["subset_failures"] += 1
            return None

        self._stats["subset_success"] += 1
        self._stats["bytes_total"] += max(0, result.bytes_written)
        self._cache[cache_key] = result
        return result

    def record_packaged_font(self, relationship_id: str | None, size_bytes: int) -> None:
        self._stats["packaged_fonts"] += 1
        self._stats["packaged_bytes"] += max(size_bytes, 0)

    def stats(self) -> Mapping[str, int]:
        return dict(self._stats)


__all__ = [
    "EmbeddedFontPayload",
    "EmbeddingPermission",
    "FontOptimisationLevel",
    "FontEmbeddingEngine",
    "FontEmbeddingRequest",
    "FontEmbeddingResult",
    "_ensure_truetype_outlines",
]
