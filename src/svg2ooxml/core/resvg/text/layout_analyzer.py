"""Text layout analysis for determining rendering strategy.

This module provides utilities to detect whether SVG text can be rendered as
native DrawingML text or requires EMF/raster fallback.

The TextLayoutAnalyzer implements heuristics to identify "simple" text layouts:
- Horizontal left-to-right flow
- Basic transforms (translation, uniform scale ≤2.0x, rotation ≤45°, skew ≤5°)
- No textPath, vertical text, or complex glyph positioning
- No per-character positioning in container or child spans

Complex layouts are rejected and should fall back to EMF for accurate rendering.

Default thresholds:
- max_rotation_deg: 45° (beyond this, text is too rotated for reliable DrawingML)
- max_skew_deg: 5° (skew distorts text, DrawingML doesn't support shear)
- max_scale_ratio: 2.0 (non-uniform scale beyond this looks distorted)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from svg2ooxml.core.resvg.usvg_tree import TextNode


@dataclass(frozen=True)
class LayoutAnalysisResult:
    """Result of text layout analysis.

    Attributes:
        is_plain: True if layout is simple enough for DrawingML
        complexity: Reason for complexity (if not plain)
        details: Optional human-readable explanation
    """
    is_plain: bool
    complexity: str
    details: str | None = None


class TextLayoutComplexity:
    """Categorizes reasons why text layout is complex.

    Note: Some advanced typography features (kerning, ligatures, glyph reuse)
    are detected via SVG attributes and style overrides, and will be treated
    as complex until DrawingML support is expanded.
    """

    # Simple layouts
    SIMPLE = "simple"

    # Complex layouts (require EMF fallback)
    HAS_TEXT_PATH = "has_text_path"
    HAS_VERTICAL_TEXT = "has_vertical_text"
    HAS_COMPLEX_TRANSFORM = "has_complex_transform"
    HAS_COMPLEX_POSITIONING = "has_complex_positioning"
    HAS_CHILD_SPAN_VERTICAL_TEXT = "has_child_span_vertical_text"
    HAS_CHILD_SPAN_COMPLEX_POSITIONING = "has_child_span_complex_positioning"

    # Advanced typography (unsupported in DrawingML path)
    HAS_KERNING = "has_kerning"
    HAS_LIGATURES = "has_ligatures"
    HAS_GLYPH_REUSE = "has_glyph_reuse"
    UNKNOWN_KERNING = HAS_KERNING
    UNKNOWN_LIGATURES = HAS_LIGATURES
    UNKNOWN_GLYPH_REUSE = HAS_GLYPH_REUSE


class TextLayoutAnalyzer:
    """Analyzes text nodes to determine if they can use native DrawingML rendering.

    Usage:
        analyzer = TextLayoutAnalyzer()
        if analyzer.is_plain_text_layout(text_node):
            # Render as native DrawingML <p:txBody>
        else:
            reason = analyzer.get_complexity_reason(text_node)
            # Fall back to EMF/raster
    """

    def __init__(
        self,
        max_rotation_deg: float = 45.0,
        max_skew_deg: float = 5.0,
        max_scale_ratio: float = 2.0,
    ):
        """Initialize the analyzer with complexity thresholds.

        Args:
            max_rotation_deg: Maximum allowed rotation in degrees (default: 45°)
            max_skew_deg: Maximum allowed skew in degrees (default: 5°)
            max_scale_ratio: Maximum ratio between x and y scale (default: 2.0)
        """
        self.max_rotation_deg = max_rotation_deg
        self.max_skew_deg = max_skew_deg
        self.max_scale_ratio = max_scale_ratio

    def is_plain_text_layout(self, node: TextNode) -> bool:
        """Check if text node can be rendered as native DrawingML text.

        This method checks both the container node and all child spans
        recursively for layout complexity.

        Args:
            node: TextNode from resvg tree

        Returns:
            True if layout is simple enough for DrawingML, False otherwise
        """
        # Check for textPath
        if self._has_text_path(node):
            return False

        # Check for vertical text
        if self._has_vertical_text(node):
            return False

        # Check for complex transforms
        if self._has_complex_transform(node):
            return False

        # Check for complex positioning
        if self._has_complex_positioning(node):
            return False

        if self._has_kerning(node) or self._has_ligatures(node) or self._has_glyph_reuse(node):
            return False

        # Check child spans recursively
        has_complex, _ = self._check_child_spans(node)
        if has_complex:
            return False

        return True

    def get_complexity_reason(self, node: TextNode) -> str:
        """Get the reason why a text layout is considered complex.

        Args:
            node: TextNode from resvg tree

        Returns:
            One of the TextLayoutComplexity constants
        """
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

        # Check child spans recursively
        has_complex, reason = self._check_child_spans(node)
        if has_complex:
            return reason

        return TextLayoutComplexity.SIMPLE

    def analyze(self, node: TextNode) -> LayoutAnalysisResult:
        """Analyze text layout and return structured result for telemetry.

        This method provides a single call that returns both the decision
        (is_plain) and the reason for complexity, suitable for telemetry
        and trace reporting.

        Args:
            node: TextNode from resvg tree

        Returns:
            LayoutAnalysisResult with is_plain, complexity, and details

        Example:
            result = analyzer.analyze(text_node)
            if result.is_plain:
                # Render as DrawingML
            else:
                logger.warning(f"Falling back to EMF: {result.details}")
        """
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
                details=f"Transform exceeds thresholds (rotation>{self.max_rotation_deg}°, skew>{self.max_skew_deg}°, scale_ratio>{self.max_scale_ratio})",
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

        # Check child spans recursively
        has_complex, reason = self._check_child_spans(node)
        if has_complex:
            if reason == TextLayoutComplexity.HAS_CHILD_SPAN_VERTICAL_TEXT:
                details = "Child span uses vertical writing mode"
            elif reason == TextLayoutComplexity.HAS_CHILD_SPAN_COMPLEX_POSITIONING:
                details = "Child span has per-character positioning"
            elif reason in {
                TextLayoutComplexity.HAS_KERNING,
                TextLayoutComplexity.HAS_LIGATURES,
                TextLayoutComplexity.HAS_GLYPH_REUSE,
            }:
                details = "Child span uses advanced typography features"
            else:
                details = "Child span has complex layout"

            return LayoutAnalysisResult(
                is_plain=False,
                complexity=reason,
                details=details,
            )

        return LayoutAnalysisResult(
            is_plain=True,
            complexity=TextLayoutComplexity.SIMPLE,
            details=None,
        )

    def _has_text_path(self, node: TextNode) -> bool:
        """Check if text uses textPath (text on a path).

        Args:
            node: TextNode to check

        Returns:
            True if text uses textPath
        """
        # Check if node has textPath child
        for child in getattr(node, "children", []):
            if hasattr(child, "tag") and child.tag and "textPath" in child.tag:
                return True

        # Check attributes for textPath reference
        attrs = getattr(node, "attributes", {}) or {}
        if "textPath" in attrs or "href" in attrs:
            return True

        return False

    def _has_vertical_text(self, node: TextNode) -> bool:
        """Check if text uses vertical writing mode.

        Args:
            node: TextNode to check

        Returns:
            True if text is vertical
        """
        attrs = getattr(node, "attributes", {}) or {}

        # Check writing-mode attribute
        writing_mode = attrs.get("writing-mode", "").lower()
        if writing_mode in ("tb", "tb-rl", "vertical-rl", "vertical-lr"):
            return True

        # Check text-orientation (used with writing-mode)
        text_orientation = attrs.get("text-orientation", "").lower()
        if "upright" in text_orientation or "sideways" in text_orientation:
            return True

        # Check glyph-orientation-vertical
        if "glyph-orientation-vertical" in attrs:
            return True

        return False

    def _has_complex_transform(self, node: TextNode) -> bool:
        """Check if text has a complex transform.

        Complex transforms include:
        - Rotation > max_rotation_deg
        - Skew > max_skew_deg
        - Non-uniform scale with ratio > max_scale_ratio

        Args:
            node: TextNode to check

        Returns:
            True if transform is too complex
        """
        transform = getattr(node, "transform", None)
        if transform is None:
            return False

        # Extract matrix components
        a = getattr(transform, "a", 1.0)
        b = getattr(transform, "b", 0.0)
        c = getattr(transform, "c", 0.0)
        d = getattr(transform, "d", 1.0)

        # Check if identity (no transform)
        if abs(a - 1.0) < 1e-6 and abs(b) < 1e-6 and abs(c) < 1e-6 and abs(d - 1.0) < 1e-6:
            return False  # Identity transform is simple

        # Calculate rotation angle
        # For a 2D rotation matrix: | cos(θ) -sin(θ) |
        #                           | sin(θ)  cos(θ) |
        # We can extract θ from atan2(b, a)
        rotation_rad = math.atan2(b, a)
        rotation_deg = abs(math.degrees(rotation_rad))

        if rotation_deg > self.max_rotation_deg:
            return True

        # Calculate scale factors
        scale_x = math.sqrt(a * a + b * b)
        scale_y = math.sqrt(c * c + d * d)

        # Check for non-uniform scale
        if scale_x > 1e-6 and scale_y > 1e-6:
            scale_ratio = max(scale_x, scale_y) / min(scale_x, scale_y)
            if scale_ratio > self.max_scale_ratio:
                return True

        # Check for skew
        # Skew is present if the dot product of the column vectors is non-zero
        # (i.e., the transform is not orthogonal)
        dot_product = a * c + b * d
        if abs(dot_product) > 1e-6:
            # Calculate skew angle
            # For small skews, skew ≈ dot_product / (scale_x * scale_y)
            if scale_x > 1e-6 and scale_y > 1e-6:
                skew_factor = abs(dot_product) / (scale_x * scale_y)
                skew_deg = abs(math.degrees(math.asin(min(1.0, skew_factor))))
                if skew_deg > self.max_skew_deg:
                    return True

        return False

    def _has_complex_positioning(self, node: TextNode) -> bool:
        """Check if text has complex glyph positioning.

        Complex positioning includes:
        - Multiple x/y position lists (per-character positioning)
        - dx/dy offsets beyond simple shift
        - Rotate attributes

        Args:
            node: TextNode to check

        Returns:
            True if positioning is too complex
        """
        attrs = getattr(node, "attributes", {}) or {}

        # Check for rotate attribute (per-character rotation)
        if "rotate" in attrs:
            return True

        # Check for complex x/y positioning
        x_attr = attrs.get("x", "")
        y_attr = attrs.get("y", "")

        # Count position values (more than 1 means per-character positioning)
        x_count = len(x_attr.split()) if x_attr else 0
        y_count = len(y_attr.split()) if y_attr else 0

        if x_count > 1 or y_count > 1:
            return True

        # Check for complex dx/dy (multiple values)
        dx_attr = attrs.get("dx", "")
        dy_attr = attrs.get("dy", "")

        dx_count = len(dx_attr.split()) if dx_attr else 0
        dy_count = len(dy_attr.split()) if dy_attr else 0

        if dx_count > 1 or dy_count > 1:
            return True

        # Additional spacing or length adjustments (unsupported in DrawingML)
        if self._has_spacing_adjustments(node):
            return True

        return False

    def _check_child_spans(self, node: TextNode) -> tuple[bool, str]:
        """Recursively check child spans for complex attributes.

        SVG allows <tspan> children to override parent attributes like
        writing-mode, dx/dy, rotate, etc. This method walks the children
        tree to detect if any child introduces complexity.

        Args:
            node: TextNode to check

        Returns:
            (has_complexity, reason) tuple where reason is one of
            TextLayoutComplexity constants if has_complexity is True,
            or empty string if False
        """
        for child in getattr(node, "children", []):
            # Check if child is a text-related element (tspan, text)
            child_tag = getattr(child, "tag", "")
            if not child_tag or not any(
                tag in child_tag.lower() for tag in ["tspan", "text"]
            ):
                continue

            # Check child's vertical text attributes
            if self._has_vertical_text(child):
                return (True, TextLayoutComplexity.HAS_CHILD_SPAN_VERTICAL_TEXT)

            if self._has_complex_transform(child):
                return (True, TextLayoutComplexity.HAS_COMPLEX_TRANSFORM)

            # Check child's positioning attributes
            if self._has_complex_positioning(child):
                return (
                    True,
                    TextLayoutComplexity.HAS_CHILD_SPAN_COMPLEX_POSITIONING,
                )

            if self._has_kerning(child):
                return (True, TextLayoutComplexity.HAS_KERNING)

            if self._has_ligatures(child):
                return (True, TextLayoutComplexity.HAS_LIGATURES)

            if self._has_glyph_reuse(child):
                return (True, TextLayoutComplexity.HAS_GLYPH_REUSE)

            # Recursively check child's children
            has_complex, reason = self._check_child_spans(child)
            if has_complex:
                return (True, reason)

        return (False, "")

    def _style_value(self, node: TextNode, name: str) -> str | None:
        attrs = getattr(node, "attributes", {}) or {}
        styles = getattr(node, "styles", {}) or {}
        return styles.get(name) or attrs.get(name)

    def _has_kerning(self, node: TextNode) -> bool:
        """Check if text uses kerning.

        Args:
            node: TextNode to check

        Returns:
            True if kerning or spacing overrides are present
        """
        kerning = self._style_value(node, "font-kerning") or self._style_value(node, "kerning")
        if kerning and kerning.strip().lower() not in {"auto", "normal"}:
            return True
        if self._font_feature_enabled(node, {"kern"}):
            return True
        return False

    def _has_ligatures(self, node: TextNode) -> bool:
        """Check if text uses ligatures.

        Args:
            node: TextNode to check

        Returns:
            True if ligature-related features are present
        """
        ligatures = self._style_value(node, "font-variant-ligatures")
        if ligatures and ligatures.strip().lower() not in {"normal", "none"}:
            return True
        if self._font_feature_enabled(node, {"liga", "clig", "dlig", "hlig"}):
            return True
        return False

    def _has_glyph_reuse(self, node: TextNode) -> bool:
        """Check if text has advanced font feature settings.

        Args:
            node: TextNode to check

        Returns:
            True if feature tags are present
        """
        features = self._style_value(node, "font-feature-settings")
        if features and features.strip().lower() != "normal":
            return True
        return False

    def _font_feature_enabled(self, node: TextNode, tokens: set[str]) -> bool:
        value = self._style_value(node, "font-feature-settings")
        if not value:
            return False
        raw = value.lower()
        if raw.strip() == "normal":
            return False
        for token in tokens:
            if token in raw:
                return True
        return False

    def _has_spacing_adjustments(self, node: TextNode) -> bool:
        # letter-spacing is supported via DrawingML spc attribute — allow it through
        word_spacing = self._style_value(node, "word-spacing")
        if word_spacing and word_spacing.strip().lower() not in {"normal", "0", "0px", "0%"}:
            return True
        text_length = self._style_value(node, "textLength")
        if text_length and text_length.strip():
            return True
        length_adjust = self._style_value(node, "lengthAdjust")
        if length_adjust and length_adjust.strip():
            return True
        return False


__all__ = ["TextLayoutAnalyzer", "TextLayoutComplexity", "LayoutAnalysisResult"]
