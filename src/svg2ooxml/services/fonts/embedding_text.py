"""Text, glyph counting, and cache-key helpers for font embedding."""

from __future__ import annotations

import os
from collections.abc import Iterable
from hashlib import sha1

from svg2ooxml.services.fonts.embedding_types import FontEmbeddingRequest


class FontEmbeddingTextMixin:
    def _glyphs_to_text(self, glyph_ids: Iterable[int]) -> str:
        chars: list[str] = []
        for glyph_id in glyph_ids:
            if 0 <= glyph_id <= 0x10FFFF:
                try:
                    chars.append(chr(glyph_id))
                except ValueError:  # pragma: no cover - extremely rare
                    continue
        return "".join(chars)

    def _prepare_subset_text(self, request: FontEmbeddingRequest) -> str:
        if request.characters:
            return "".join(request.characters)
        return self._glyphs_to_text(request.glyph_ids)

    def _glyph_count(self, request: FontEmbeddingRequest) -> int:
        if request.glyph_ids:
            return len(set(request.glyph_ids))
        if request.characters:
            return len(set(request.characters))
        return 0

    def _cache_key(self, request: FontEmbeddingRequest) -> str:
        digest = sha1()
        digest.update(os.fsencode(request.font_path))
        digest.update(str(request.glyph_ids).encode("utf-8"))
        digest.update("/".join(request.characters).encode("utf-8"))
        digest.update(request.subset_strategy.encode("utf-8"))
        digest.update(b"1" if request.preserve_hinting else b"0")
        digest.update(request.optimisation.value.encode("utf-8"))
        return digest.hexdigest()


__all__ = ["FontEmbeddingTextMixin"]
