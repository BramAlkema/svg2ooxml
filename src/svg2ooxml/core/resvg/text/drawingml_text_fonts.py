"""Font service integration for ``DrawingMLTextGenerator``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from svg2ooxml.core.resvg.text.drawingml_text_properties import _parse_font_weight

if TYPE_CHECKING:
    from svg2ooxml.core.resvg.usvg_tree import TextNode
    from svg2ooxml.services.fonts.embedding import FontEmbeddingResult
    from svg2ooxml.services.fonts.service import FontMatch


class DrawingMLTextFontMixin:
    """Resolve and embed fonts for resvg DrawingML text generation."""

    def resolve_font(
        self,
        node: TextNode,
        fallback_chain: tuple[str, ...] = (),
    ) -> FontMatch | None:
        """Resolve font for text node using FontService."""
        if not self._font_service or not node.text_style:
            return None

        from svg2ooxml.services.fonts.service import FontQuery

        text_style = node.text_style
        primary_family = (
            text_style.font_families[0] if text_style.font_families else "Arial"
        )
        query = FontQuery(
            family=primary_family,
            weight=_parse_font_weight(text_style.font_weight),
            style=text_style.font_style or "normal",
            fallback_chain=fallback_chain,
        )
        return self._font_service.find_font(query)

    def embed_font(
        self,
        node: TextNode,
        match: FontMatch,
    ) -> FontEmbeddingResult | None:
        """Embed font using FontEmbeddingEngine."""
        if not self._embedding_engine:
            return None

        from svg2ooxml.services.fonts.embedding import FontEmbeddingRequest

        characters = set(node.text_content or "")
        if not characters:
            return None

        metadata: dict[str, object] = {}
        if "font_data" in match.metadata:
            metadata["font_data"] = match.metadata["font_data"]

        request = FontEmbeddingRequest(
            font_path=match.path or "unknown",
            characters=tuple(characters),
            preserve_hinting=True,
            subset_strategy="glyph",
            metadata=metadata,
        )
        return self._embedding_engine.subset_font(request)


__all__ = ["DrawingMLTextFontMixin"]
