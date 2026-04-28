"""Subset strategy implementations for font embedding."""

from __future__ import annotations

import logging
from pathlib import Path

from svg2ooxml.services.fonts.embedding_conversion import ensure_truetype_outlines
from svg2ooxml.services.fonts.embedding_types import (
    EmbeddingPermission,
    FontEmbeddingRequest,
    FontEmbeddingResult,
)
from svg2ooxml.services.fonts.eot import EOTConversionError
from svg2ooxml.services.fonts.fontforge_utils import FONTFORGE_AVAILABLE, open_font

logger = logging.getLogger(__name__)


class FontEmbeddingSubsetMixin:
    def _subset_copy(
        self,
        request: FontEmbeddingRequest,
        permission: EmbeddingPermission,
    ) -> FontEmbeddingResult | None:
        if "font_data" in request.metadata:
            data = request.metadata["font_data"]
            if not isinstance(data, bytes):
                logger.debug("Invalid font_data type in metadata: %s", type(data))
                return None
        else:
            try:
                data = Path(request.font_path).read_bytes()
            except OSError as exc:  # pragma: no cover - depends on local filesystem
                logger.debug("Failed to read font for direct embedding: %s", exc)
                return None

        data = ensure_truetype_outlines(data, request.font_path)

        metadata = {
            "subset_strategy": request.subset_strategy,
            "preserve_hinting": request.preserve_hinting,
            "font_path": request.font_path,
            "glyph_ids": request.glyph_ids,
            "characters": request.characters,
            "font_data": data,
            "optimisation": request.optimisation.value,
            "permission": permission.value,
        }
        metadata.update(request.metadata)

        return FontEmbeddingResult(
            relationship_id=None,
            subset_path=None,
            glyph_count=self._glyph_count(request),
            bytes_written=len(data),
            permission=permission,
            optimisation=request.optimisation,
            packaging_metadata=metadata,
        )

    def _subset_with_fontforge(
        self,
        request: FontEmbeddingRequest,
        text_payload: str,
        permission: EmbeddingPermission,
    ) -> FontEmbeddingResult | None:
        if not FONTFORGE_AVAILABLE:  # pragma: no cover - optional dependency guard
            logger.debug("FontForge not available; cannot subset font %s", request.font_path)
            return None

        subset_bytes = None
        try:
            if "font_data" in request.metadata:
                font_data = request.metadata["font_data"]
                if not isinstance(font_data, bytes):
                    logger.debug("Invalid font_data type in metadata: %s", type(font_data))
                    return None
                with open_font(font_data, suffix=".ttf") as font:
                    subset_bytes = self._perform_subsetting(font, text_payload)
            else:
                font_suffix = Path(request.font_path).suffix or ".ttf"
                with open_font(request.font_path, suffix=font_suffix) as font:
                    subset_bytes = self._perform_subsetting(font, text_payload)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("FontForge subsetting failed: %s", exc)
            subset_bytes = None

        if subset_bytes is None:
            return None

        subset_bytes = ensure_truetype_outlines(subset_bytes, request.font_path)

        try:
            payload = self._build_eot_payload(subset_bytes, request)
        except EOTConversionError as exc:
            logger.debug("EOT conversion failed: %s", exc)
            return None

        metadata = {
            "subset_strategy": request.subset_strategy,
            "preserve_hinting": request.preserve_hinting,
            "font_path": request.font_path,
            "glyph_ids": request.glyph_ids,
            "characters": request.characters,
            "subset_bytes": subset_bytes,
            "font_data": payload.eot_bytes,
            "eot_bytes": payload.eot_bytes,
            "font_guid": str(payload.guid) if payload.guid else None,
            "font_root_string": payload.root_string,
            "font_style_kind": payload.style_kind,
            "font_style_flags": dict(payload.style_flags),
            "subset_prefix": payload.subset_prefix,
            "font_charset": payload.charset,
            "font_panose": payload.panose,
            "font_unicode_ranges": payload.unicode_ranges,
            "font_codepage_ranges": payload.codepage_ranges,
            "font_pitch_family": payload.pitch_family,
            "optimisation": request.optimisation.value,
            "permission": permission.value,
        }
        metadata.update(request.metadata)

        return FontEmbeddingResult(
            relationship_id=None,
            subset_path=None,
            glyph_count=self._glyph_count(request),
            bytes_written=len(subset_bytes),
            permission=permission,
            optimisation=request.optimisation,
            packaging_metadata=metadata,
        )


__all__ = ["FontEmbeddingSubsetMixin"]
