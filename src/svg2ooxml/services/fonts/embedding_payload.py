"""EOT payload construction for font embedding."""

from __future__ import annotations

import uuid
from pathlib import Path

from svg2ooxml.services.fonts.embedding_style import (
    derive_pitch_family as _derive_pitch_family,
)
from svg2ooxml.services.fonts.embedding_style import (
    style_flags_from_metadata as _style_flags_from_metadata,
)
from svg2ooxml.services.fonts.embedding_style import (
    style_kind_from_metadata as _style_kind_from_metadata,
)
from svg2ooxml.services.fonts.embedding_style import (
    style_name_from_kind as _style_name_from_kind,
)
from svg2ooxml.services.fonts.embedding_types import (
    EmbeddedFontPayload,
    FontEmbeddingRequest,
)
from svg2ooxml.services.fonts.eot import build_eot


class FontEmbeddingPayloadMixin:
    def _build_eot_payload(
        self,
        subset_bytes: bytes,
        request: FontEmbeddingRequest,
    ) -> EmbeddedFontPayload:
        metadata = request.metadata or {}
        style_kind = _style_kind_from_metadata(metadata)
        style_name = _style_name_from_kind(style_kind)
        guid = uuid.uuid4()
        resolved_family = (
            metadata.get("resolved_family")
            or metadata.get("font_family")
            or Path(request.font_path).stem
            or "EmbeddedFont"
        )
        eot_result = build_eot(
            subset_bytes,
            resolved_family=resolved_family,
            resolved_style=style_name,
            root_string=metadata.get("font_root_string"),
            guid=guid,
        )
        style_flags = _style_flags_from_metadata(metadata, style_kind)
        pitch_family = _derive_pitch_family(eot_result.panose, style_flags)
        return EmbeddedFontPayload(
            subset_bytes=subset_bytes,
            eot_bytes=eot_result.data,
            guid=eot_result.guid,
            root_string=eot_result.root_string,
            style_kind=style_kind,
            style_flags=style_flags,
            subset_prefix=metadata.get("subset_prefix"),
            charset=eot_result.charset,
            panose=eot_result.panose,
            unicode_ranges=eot_result.unicode_ranges,
            codepage_ranges=eot_result.codepage_ranges,
            fs_type=eot_result.fs_type,
            pitch_family=pitch_family,
        )


__all__ = ["FontEmbeddingPayloadMixin"]
