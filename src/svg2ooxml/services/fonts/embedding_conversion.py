"""Font byte conversion helpers for Office embedding."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def ensure_truetype_outlines(data: bytes, source: str) -> bytes:
    """Convert CFF-flavoured OpenType bytes to TrueType outlines when possible."""
    try:
        from svg2ooxml.services.fonts.otf2ttf import convert_font_bytes_for_embedding
    except ImportError:
        logger.warning(
            "fontTools unavailable; cannot convert %s to TrueType for embedding. "
            "Install the 'slides' extra to enable OTF->TTF conversion.",
            source,
        )
        return data

    try:
        return convert_font_bytes_for_embedding(data)
    except Exception as exc:
        logger.warning("OTF->TTF conversion failed for %s: %s", source, exc)
        return data


__all__ = ["ensure_truetype_outlines"]
