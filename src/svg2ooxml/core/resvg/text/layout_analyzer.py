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
    from svg2ooxml.core.resvg.usvg_tree import TextNode, BaseNode


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
    cannot currently be detected because the resvg API doesn't expose this data.
    These are marked as TODO and will be implemented when pyportresvg bindings
    are enhanced. Until then, we may green-light some complex text that should
    fall back to EMF.
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

    # TODO: Cannot detect yet (resvg API limitation)
    # When these are detectable, add checks to reject complex typography:
    UNKNOWN_KERNING = "unknown_kerning"  # TODO: Requires resvg glyph positioning API
    UNKNOWN_LIGATURES = "unknown_ligatures"  # TODO: Requires resvg font feature API
    UNKNOWN_GLYPH_REUSE = "unknown_glyph_reuse"  # TODO: Requires resvg glyph mapping API


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

    def is_plain_text_layout(self, node: "TextNode") -> bool:
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

        # Check child spans recursively
        has_complex, _ = self._check_child_spans(node)
        if has_complex:
            return False

        # TODO: Check for kerning/ligatures when resvg API exposes this
        # For now, we assume simple cases don't have complex typography

        return True

    def get_complexity_reason(self, node: "TextNode") -> str:
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

        # Check child spans recursively
        has_complex, reason = self._check_child_spans(node)
        if has_complex:
            return reason

        return TextLayoutComplexity.SIMPLE

    def analyze(self, node: "TextNode") -> LayoutAnalysisResult:
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

        # Check child spans recursively
        has_complex, reason = self._check_child_spans(node)
        if has_complex:
            if reason == TextLayoutComplexity.HAS_CHILD_SPAN_VERTICAL_TEXT:
                details = "Child span uses vertical writing mode"
            elif reason == TextLayoutComplexity.HAS_CHILD_SPAN_COMPLEX_POSITIONING:
                details = "Child span has per-character positioning"
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

    def _has_text_path(self, node: "TextNode") -> bool:
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

    def _has_vertical_text(self, node: "TextNode") -> bool:
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

    def _has_complex_transform(self, node: "TextNode") -> bool:
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

    def _has_complex_positioning(self, node: "TextNode") -> bool:
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

        # TODO: Check for glyph reuse (when resvg API exposes this)
        # This would indicate advanced typography features

        return False

    def _check_child_spans(self, node: "TextNode") -> tuple[bool, str]:
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

            # Check child's positioning attributes
            if self._has_complex_positioning(child):
                return (
                    True,
                    TextLayoutComplexity.HAS_CHILD_SPAN_COMPLEX_POSITIONING,
                )

            # Recursively check child's children
            has_complex, reason = self._check_child_spans(child)
            if has_complex:
                return (True, reason)

        return (False, "")

    # TODO: Future methods when resvg API improves

    def _has_kerning(self, node: "TextNode") -> bool:
        """Check if text uses kerning.

        TODO: Implement when resvg API exposes kerning information.

        Args:
            node: TextNode to check

        Returns:
            False (not detectable yet)
        """
        # Placeholder for future implementation
        # When pyportresvg bindings expose kerning data, check here
        return False

    def _has_ligatures(self, node: "TextNode") -> bool:
        """Check if text uses ligatures.

        TODO: Implement when resvg API exposes ligature information.

        Args:
            node: TextNode to check

        Returns:
            False (not detectable yet)
        """
        # Placeholder for future implementation
        # When pyportresvg bindings expose ligature data, check here
        return False

    def _has_glyph_reuse(self, node: "TextNode") -> bool:
        """Check if text has complex glyph positioning/reuse.

        TODO: Implement when resvg API exposes glyph positioning data.

        Args:
            node: TextNode to check

        Returns:
            False (not detectable yet)
        """
        # Placeholder for future implementation
        # When pyportresvg bindings expose glyph data, check here
        return False


__all__ = ["TextLayoutAnalyzer", "TextLayoutComplexity", "LayoutAnalysisResult"]
