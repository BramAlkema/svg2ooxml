"""Text layout complexity result types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayoutAnalysisResult:
    """Result of text layout analysis."""

    is_plain: bool
    complexity: str
    details: str | None = None


class TextLayoutComplexity:
    """Categorizes reasons why text layout is complex."""

    SIMPLE = "simple"
    HAS_TEXT_PATH = "has_text_path"
    HAS_VERTICAL_TEXT = "has_vertical_text"
    HAS_COMPLEX_TRANSFORM = "has_complex_transform"
    HAS_COMPLEX_POSITIONING = "has_complex_positioning"
    HAS_CHILD_SPAN_VERTICAL_TEXT = "has_child_span_vertical_text"
    HAS_CHILD_SPAN_COMPLEX_POSITIONING = "has_child_span_complex_positioning"
    HAS_KERNING = "has_kerning"
    HAS_LIGATURES = "has_ligatures"
    HAS_GLYPH_REUSE = "has_glyph_reuse"
    UNKNOWN_KERNING = HAS_KERNING
    UNKNOWN_LIGATURES = HAS_LIGATURES
    UNKNOWN_GLYPH_REUSE = HAS_GLYPH_REUSE


__all__ = ["LayoutAnalysisResult", "TextLayoutComplexity"]
