"""OpenType embedding permission helpers."""

from __future__ import annotations

from pathlib import Path

from svg2ooxml.services.fonts.embedding_types import EmbeddingPermission
from svg2ooxml.services.fonts.fontforge_utils import (
    FONTFORGE_AVAILABLE,
    get_table_data,
    open_font,
)
from svg2ooxml.services.fonts.opentype_utils import parse_os2_table


def coerce_embedding_permission(value: object) -> EmbeddingPermission:
    if isinstance(value, EmbeddingPermission):
        return value
    if isinstance(value, str) and value in EmbeddingPermission._value2member_map_:
        return EmbeddingPermission(value)
    return EmbeddingPermission.UNKNOWN


class FontEmbeddingPermissionMixin:
    def _read_embedding_permission(
        self,
        font_path: str,
        font_data: bytes | None = None,
    ) -> EmbeddingPermission:
        if not FONTFORGE_AVAILABLE:  # pragma: no cover - optional dependency guard
            return EmbeddingPermission.UNKNOWN
        try:
            if font_data is not None:
                with open_font(font_data, suffix=".ttf") as font:
                    os2_table = get_table_data(font, "OS/2")
            else:
                font_suffix = Path(font_path).suffix or ".ttf"
                with open_font(font_path, suffix=font_suffix) as font:
                    os2_table = get_table_data(font, "OS/2")
        except Exception:
            return EmbeddingPermission.UNKNOWN
        try:
            os2 = parse_os2_table(os2_table)
            fs_type = int(os2.fs_type or 0)
            if fs_type & 0x0002:
                return EmbeddingPermission.RESTRICTED
            if fs_type & 0x0004:
                return EmbeddingPermission.PREVIEW_PRINT
            if fs_type & 0x0008:
                return EmbeddingPermission.EDITABLE
            if fs_type & 0x0100:
                return EmbeddingPermission.NO_SUBSETTING
            if fs_type & 0x0200:
                return EmbeddingPermission.BITMAP_ONLY
            return EmbeddingPermission.INSTALLABLE
        except Exception:  # pragma: no cover - defensive fallback
            return EmbeddingPermission.UNKNOWN


__all__ = ["FontEmbeddingPermissionMixin", "coerce_embedding_permission"]
