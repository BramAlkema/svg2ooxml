"""Text layout analysis for determining rendering strategy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from svg2ooxml.core.resvg.text.layout_checks import TextLayoutChecksMixin
from svg2ooxml.core.resvg.text.layout_complexity import (
    LayoutAnalysisResult,
    TextLayoutComplexity,
)

if TYPE_CHECKING:
    from svg2ooxml.core.resvg.usvg_tree import TextNode


class TextLayoutAnalyzer(TextLayoutChecksMixin):
    """Analyzes text nodes to determine if they can use native DrawingML rendering."""

    def __init__(
        self,
        max_rotation_deg: float = 45.0,
        max_skew_deg: float = 5.0,
        max_scale_ratio: float = 2.0,
    ):
        self.max_rotation_deg = max_rotation_deg
        self.max_skew_deg = max_skew_deg
        self.max_scale_ratio = max_scale_ratio

    def is_plain_text_layout(self, node: TextNode) -> bool:
        """Check if text node can be rendered as native DrawingML text."""
        if self._has_text_path(node):
            return False
        if self._has_vertical_text(node):
            return False
        if self._has_complex_transform(node):
            return False
        if self._has_complex_positioning(node):
            return False
        if self._has_kerning(node) or self._has_ligatures(node) or self._has_glyph_reuse(node):
            return False

        has_complex, _ = self._check_child_spans(node)
        return not has_complex

    def get_complexity_reason(self, node: TextNode) -> str:
        """Get the reason why a text layout is considered complex."""
        if self._has_text_path(node):
            return TextLayoutComplexity.HAS_TEXT_PATH
        if self._has_vertical_text(node):
            return TextLayoutComplexity.HAS_VERTICAL_TEXT
        if self._has_complex_transform(node):
            return TextLayoutComplexity.HAS_COMPLEX_TRANSFORM
        if self._has_complex_positioning(node):
            return TextLayoutComplexity.HAS_COMPLEX_POSITIONING
        if self._has_kerning(node):
            return TextLayoutComplexity.HAS_KERNING
        if self._has_ligatures(node):
            return TextLayoutComplexity.HAS_LIGATURES
        if self._has_glyph_reuse(node):
            return TextLayoutComplexity.HAS_GLYPH_REUSE

        has_complex, reason = self._check_child_spans(node)
        if has_complex:
            return reason
        return TextLayoutComplexity.SIMPLE

    def analyze(self, node: TextNode) -> LayoutAnalysisResult:
        """Analyze text layout and return structured result for telemetry."""
        direct_result = self._direct_complexity_result(node)
        if direct_result is not None:
            return direct_result

        has_complex, reason = self._check_child_spans(node)
        if has_complex:
            return LayoutAnalysisResult(
                is_plain=False,
                complexity=reason,
                details=_child_span_details(reason),
            )

        return LayoutAnalysisResult(
            is_plain=True,
            complexity=TextLayoutComplexity.SIMPLE,
            details=None,
        )

    def _direct_complexity_result(self, node: TextNode) -> LayoutAnalysisResult | None:
        if self._has_text_path(node):
            return LayoutAnalysisResult(
                is_plain=False,
                complexity=TextLayoutComplexity.HAS_TEXT_PATH,
                details="Text uses textPath (text on a path)",
            )
        if self._has_vertical_text(node):
            return LayoutAnalysisResult(
                is_plain=False,
                complexity=TextLayoutComplexity.HAS_VERTICAL_TEXT,
                details="Text uses vertical writing mode",
            )
        if self._has_complex_transform(node):
            return LayoutAnalysisResult(
                is_plain=False,
                complexity=TextLayoutComplexity.HAS_COMPLEX_TRANSFORM,
                details=(
                    "Transform exceeds thresholds "
                    f"(rotation>{self.max_rotation_deg}°, "
                    f"skew>{self.max_skew_deg}°, "
                    f"scale_ratio>{self.max_scale_ratio})"
                ),
            )
        if self._has_complex_positioning(node):
            return LayoutAnalysisResult(
                is_plain=False,
                complexity=TextLayoutComplexity.HAS_COMPLEX_POSITIONING,
                details="Text has per-character positioning (multiple x/y/dx/dy values or rotate attribute)",
            )
        if self._has_kerning(node):
            return LayoutAnalysisResult(
                is_plain=False,
                complexity=TextLayoutComplexity.HAS_KERNING,
                details="Text uses kerning or spacing overrides unsupported in DrawingML",
            )
        if self._has_ligatures(node):
            return LayoutAnalysisResult(
                is_plain=False,
                complexity=TextLayoutComplexity.HAS_LIGATURES,
                details="Text uses ligatures or font feature settings unsupported in DrawingML",
            )
        if self._has_glyph_reuse(node):
            return LayoutAnalysisResult(
                is_plain=False,
                complexity=TextLayoutComplexity.HAS_GLYPH_REUSE,
                details="Text uses advanced font features unsupported in DrawingML",
            )
        return None


def _child_span_details(reason: str) -> str:
    if reason == TextLayoutComplexity.HAS_CHILD_SPAN_VERTICAL_TEXT:
        return "Child span uses vertical writing mode"
    if reason == TextLayoutComplexity.HAS_CHILD_SPAN_COMPLEX_POSITIONING:
        return "Child span has per-character positioning"
    if reason in {
        TextLayoutComplexity.HAS_KERNING,
        TextLayoutComplexity.HAS_LIGATURES,
        TextLayoutComplexity.HAS_GLYPH_REUSE,
    }:
        return "Child span uses advanced typography features"
    return "Child span has complex layout"


__all__ = ["TextLayoutAnalyzer", "TextLayoutComplexity", "LayoutAnalysisResult"]
