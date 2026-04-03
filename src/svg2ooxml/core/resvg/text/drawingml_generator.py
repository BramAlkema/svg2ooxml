"""DrawingML text body generator for plain text nodes.

This module converts simple SVG text elements (validated by TextLayoutAnalyzer)
into native DrawingML <p:txBody> format for PowerPoint.

The generator creates valid DrawingML structures with proper font properties,
text runs, and paragraph formatting suitable for rendering in PowerPoint.

All unit conversions use the centralized UnitConverter system for consistency.

The generator optionally integrates with FontService for font resolution and
FontEmbeddingEngine for font subsetting/embedding when configured.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from lxml import etree  # For type annotations

# Import centralized color model for hex conversion
from collections.abc import Callable

from svg2ooxml.color.models import Color as CentralizedColor

# Import centralized unit conversion constants
from svg2ooxml.common.conversions.bidi import is_rtl_text
from svg2ooxml.common.conversions.opacity import opacity_to_ppt
from svg2ooxml.common.units import px_to_emu

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, p_elem, to_string

if TYPE_CHECKING:
    from svg2ooxml.core.resvg.painting.paint import (
        Color as ResvgColor,
        FillStyle,
        PaintReference,
        StrokeStyle,
        TextStyle,
    )
    from svg2ooxml.core.resvg.usvg_tree import TextNode
    from svg2ooxml.ir.paint import Paint
    from svg2ooxml.services.fonts.embedding import (
        FontEmbeddingEngine,
        FontEmbeddingResult,
    )
    from svg2ooxml.services.fonts.service import FontMatch, FontService

# DrawingML font size is specified in hundredths of a point
# 1 point = 100 hundredths = EMU_PER_POINT (12,700) EMUs
# This constant defines the DrawingML-to-points relationship,
# while EMU_PER_POINT provides the centralized points-to-EMU conversion
DRAWINGML_HUNDREDTHS_PER_POINT = 100


def _parse_font_weight(font_weight: str | None) -> int:
    """Parse SVG font-weight to numeric value (100-900).

    Args:
        font_weight: SVG font-weight value (normal, bold, 100-900, etc.)

    Returns:
        Numeric weight value (100-900), default 400 for normal
    """
    if not font_weight:
        return 400  # normal

    weight_lower = font_weight.lower().strip()

    # Handle named weights
    if weight_lower == "normal":
        return 400
    if weight_lower == "bold":
        return 700
    if weight_lower == "bolder":
        return 700  # Simplified (should be relative to parent)
    if weight_lower == "lighter":
        return 300  # Simplified (should be relative to parent)

    # Handle numeric weights (100-900)
    try:
        weight_num = int(weight_lower)
        # Clamp to valid range
        return max(100, min(900, weight_num))
    except ValueError:
        return 400  # Default to normal


def _map_font_weight(font_weight: str | None) -> bool:
    """Convert SVG font-weight to bold flag.

    Args:
        font_weight: SVG font-weight value (normal, bold, 100-900, etc.)

    Returns:
        True if weight is bold (>= 700), False otherwise
    """
    return _parse_font_weight(font_weight) >= 700


def _map_font_style(font_style: str | None) -> bool:
    """Convert SVG font-style to italic flag.

    Args:
        font_style: SVG font-style value (normal, italic, oblique)

    Returns:
        True if style is italic or oblique, False otherwise
    """
    if not font_style:
        return False

    style_lower = font_style.lower().strip()
    return style_lower in ("italic", "oblique")


def _color_to_hex(color: ResvgColor | None) -> str:
    """Convert resvg Color to 6-character uppercase sRGB hex string.

    Uses the centralized Color model from svg2ooxml.color.models for consistent
    color conversion across the codebase. The centralized Color.to_hex() method
    handles rounding and clamping properly.

    Args:
        color: Resvg Color object with r, g, b components (0.0-1.0 normalized)

    Returns:
        6-character uppercase hex color string (e.g., "FF0000" for red)
    """
    if color is None:
        return "000000"  # Default to black

    # Convert resvg Color to centralized Color model
    centralized = CentralizedColor(r=color.r, g=color.g, b=color.b, a=color.a)

    # Use centralized to_hex() method (returns "#rrggbb" in lowercase)
    hex_with_hash = centralized.to_hex(include_alpha=False)

    # Remove "#" prefix and convert to uppercase for DrawingML
    return hex_with_hash[1:].upper()


def _font_size_pt_to_drawingml(size_pt: float) -> int:
    """Convert font size from points to DrawingML hundredths of a point.

    DrawingML specifies font sizes in hundredths of a point (1/7200 inch).
    For example: 12pt = 1200, 10.5pt = 1050.

    This conversion uses the centralized unit system constants:
    - 1 point = EMU_PER_POINT (12,700) EMUs (from common.units.scalars)
    - 1 point = DRAWINGML_HUNDREDTHS_PER_POINT (100) hundredths (DrawingML spec)

    Uses round() for fidelity: 12.999pt → 1300 (not 1299).
    Returns at least 1 to avoid zero-size fonts.

    Args:
        size_pt: Font size in points (positive value expected)

    Returns:
        Font size in DrawingML units (hundredths of a point), minimum 1
    """
    if size_pt <= 0:
        raise ValueError(f"Font size must be positive, got {size_pt}")

    # Convert points to hundredths with rounding
    # Uses DRAWINGML_HUNDREDTHS_PER_POINT which is tied to EMU_PER_POINT
    hundredths = round(size_pt * DRAWINGML_HUNDREDTHS_PER_POINT)

    # Ensure at least 1 (DrawingML minimum)
    return max(1, hundredths)


class DrawingMLTextGenerator:
    """Generates DrawingML <p:txBody> elements from simple SVG text nodes.

    This generator is designed for plain horizontal text that has passed
    complexity checks from TextLayoutAnalyzer. It creates native PowerPoint
    text structures with proper font properties and formatting.

    Optionally integrates with FontService for font resolution and
    FontEmbeddingEngine for font subsetting/embedding.

    Usage:
        # Basic usage (no font services)
        generator = DrawingMLTextGenerator()
        xml = generator.generate_text_body(text_node)

        # With font services
        generator = DrawingMLTextGenerator(
            font_service=font_service,
            embedding_engine=embedding_engine
        )
        xml = generator.generate_text_body(text_node)
    """

    def __init__(
        self,
        font_service: FontService | None = None,
        embedding_engine: FontEmbeddingEngine | None = None,
        paint_resolver: Callable[[PaintReference], Paint | None] | None = None,
    ) -> None:
        """Initialize the DrawingML text generator.

        Args:
            font_service: Optional FontService for font resolution
            embedding_engine: Optional FontEmbeddingEngine for font subsetting
            paint_resolver: Optional callback to resolve PaintReference (gradient/pattern)
                to an IR Paint object (LinearGradientPaint, RadialGradientPaint, etc.)
        """
        self._font_service = font_service
        self._embedding_engine = embedding_engine
        self._paint_resolver = paint_resolver

    def generate_wordart_text_body(self, node: TextNode, preset: str) -> str:
        """Generate <p:txBody> with prstTxWarp for WordArt rendering.

        Creates a text body with the specified WordArt warp preset on <a:bodyPr>,
        producing native editable text instead of EMF fallback.

        Args:
            node: TextNode from resvg tree
            preset: DrawingML warp preset name (e.g. "textWave1", "textArchUp")

        Returns:
            Complete DrawingML XML string for <p:txBody> with prstTxWarp
        """
        txBody = p_elem("txBody")
        bodyPr = a_sub(txBody, "bodyPr")
        bodyPr.set("wrap", "none")
        bodyPr.set("lIns", "0")
        bodyPr.set("tIns", "0")
        bodyPr.set("rIns", "0")
        bodyPr.set("bIns", "0")
        bodyPr.set("anchor", "t")
        warp = a_sub(bodyPr, "prstTxWarp", prst=preset)
        a_sub(warp, "avLst")
        a_sub(txBody, "lstStyle")
        p = a_sub(txBody, "p")
        pPr = a_sub(p, "pPr")
        if self._is_node_rtl(node):
            pPr.set("rtl", "1")

        self._generate_runs_into_parent(node, p)

        a_sub(p, "endParaRPr")
        return to_string(txBody)

    def generate_text_body(self, node: TextNode) -> str:
        """Generate <p:txBody> DrawingML for a text node.

        This creates a complete text body structure suitable for embedding
        in a PowerPoint shape. The structure includes:
        - <a:bodyPr/> for text box properties
        - <a:lstStyle/> for list styling
        - <a:p> paragraph with text runs

        Uses xml_builder module for safe XML generation with automatic escaping.

        Args:
            node: TextNode from resvg tree (must be validated as plain first)

        Returns:
            Complete DrawingML XML string for <p:txBody>

        Example:
            >>> node = TextNode(text_content="Hello World", ...)
            >>> xml = generator.generate_text_body(node)
            >>> print(xml)
            <p:txBody><a:bodyPr/><a:lstStyle/><a:p>...</a:p></p:txBody>
        """
        # Build using xml_builder for safe XML generation
        txBody = p_elem("txBody")
        a_sub(txBody, "bodyPr")
        a_sub(txBody, "lstStyle")
        p = a_sub(txBody, "p")

        # Add paragraph properties with RTL if detected
        pPr = a_sub(p, "pPr")
        if self._is_node_rtl(node):
            pPr.set("rtl", "1")

        # Generate runs and append to paragraph
        self._generate_runs_into_parent(node, p)

        # Serialize to string with namespace prefixes
        return to_string(txBody)

    def generate_runs_xml(self, node: TextNode) -> str:
        """Generate <a:r>/<a:br> XML for a text node.

        This helper returns only the run fragments that belong inside the
        paragraph, suitable for plugging into existing text templates.
        """
        paragraph = a_elem("p")
        self._generate_runs_into_parent(node, paragraph)
        return "".join(to_string(child) for child in paragraph)

    def _generate_runs_into_parent(
        self, node: TextNode, parent: etree._Element
    ) -> None:
        """Generate text run elements and append to parent paragraph.

        Generates one run per text segment, including simple <tspan> style
        overrides that inherit from the parent. Complex positioning and
        advanced typography remain gated by TextLayoutAnalyzer.

        Uses lxml for safe XML generation with automatic text escaping.

        Args:
            node: TextNode with text_content and optional text_style
            parent: Parent <a:p> element to append runs to
        """
        segments = self._collect_text_segments(node)

        # Empty text - use end paragraph marker
        if not segments:
            a_sub(parent, "endParaRPr")
            return

        for text, text_style, fill_style, stroke_style, preserve_space in segments:
            normalized = self._normalize_text_segment(
                text, preserve_space=preserve_space
            )
            if not normalized:
                continue
            parts = normalized.split("\n")
            for index, part in enumerate(parts):
                if index > 0:
                    a_sub(parent, "br")

                r = a_sub(parent, "r")
                rPr = a_sub(r, "rPr")
                self._populate_run_properties(rPr, text_style, fill_style, stroke_style)

                t = a_sub(r, "t")
                text_value = part if part else " "
                preserve = (
                    text_value == " "
                    or text_value.startswith(" ")
                    or text_value.endswith(" ")
                )
                t.text = text_value
                if preserve:
                    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

    def _populate_run_properties(
        self,
        rPr: etree._Element,
        text_style: TextStyle | None,
        fill_style: FillStyle | None,
        stroke_style: StrokeStyle | None = None,
    ) -> None:
        """Populate <a:rPr> run properties element from text style.

        Maps SVG text properties to DrawingML attributes and child elements:
        - font-family → typeface (lxml handles escaping automatically)
        - font-size → sz (in hundredths of a point, rounded)
        - font-weight → b
        - font-style → i
        - stroke/outline → ln (MUST come before fill)
        - fill color → solidFill

        Uses lxml for safe attribute escaping (no need for manual escaping).

        Args:
            rPr: The <a:rPr> element to populate
            text_style: TextStyle with font properties
            fill_style: FillStyle with color information
            stroke_style: Optional StrokeStyle for outlines
        """
        # 1. Outline (stroke) - MUST come before fill per DrawingML spec
        if stroke_style and stroke_style.width is not None and stroke_style.width > 0:
            ln = a_sub(rPr, "ln", w=str(round(px_to_emu(stroke_style.width))))
            stroke_grad_elem = self._resolve_gradient_fill(stroke_style.reference)
            if stroke_grad_elem is not None:
                ln.append(stroke_grad_elem)
            else:
                stroke_color = stroke_style.color or getattr(fill_style, "color", None)
                if stroke_color:
                    hex_color = _color_to_hex(stroke_color)
                    strokeFill = a_sub(ln, "solidFill")
                    stroke_alpha = opacity_to_ppt(stroke_style.opacity)
                    if stroke_alpha < 100000:
                        srgbClr = a_sub(strokeFill, "srgbClr", val=hex_color)
                        a_sub(srgbClr, "alpha", val=str(stroke_alpha))
                    else:
                        a_sub(strokeFill, "srgbClr", val=hex_color)

        # 2. Fill — gradient or solid color
        fill_grad_elem = self._resolve_gradient_fill(
            fill_style.reference if fill_style else None
        )
        if fill_grad_elem is not None:
            rPr.append(fill_grad_elem)
        elif fill_style and fill_style.color:
            hex_color = _color_to_hex(fill_style.color)
            solidFill = a_sub(rPr, "solidFill")
            fill_alpha = opacity_to_ppt(fill_style.opacity)
            if fill_alpha < 100000:
                srgbClr = a_sub(solidFill, "srgbClr", val=hex_color)
                a_sub(srgbClr, "alpha", val=str(fill_alpha))
            else:
                a_sub(solidFill, "srgbClr", val=hex_color)

        if text_style:
            # Font size in hundredths of a point (e.g., 12pt = 1200)
            # Uses centralized conversion with proper rounding
            if text_style.font_size is not None and text_style.font_size > 0:
                try:
                    size_hundredths = _font_size_pt_to_drawingml(text_style.font_size)
                    rPr.set("sz", str(size_hundredths))
                except ValueError:
                    # Invalid font size, skip attribute
                    pass

            # Bold
            if _map_font_weight(text_style.font_weight):
                rPr.set("b", "1")

            # Italic
            if _map_font_style(text_style.font_style):
                rPr.set("i", "1")

            # Text decorations (underline, strikethrough)
            if text_style.text_decoration:
                deco = text_style.text_decoration.lower()
                if "underline" in deco:
                    rPr.set("u", "sng")
                if "line-through" in deco:
                    rPr.set("strike", "sngStrike")

            # Letter-spacing → spc (hundredths of a point)
            if text_style.letter_spacing is not None:
                # Convert px to hundredths of a point: px * (72/96) * 100
                spc = round(text_style.letter_spacing * 75)
                rPr.set("spc", str(spc))

            # Font family (lxml handles special characters like & automatically)
            if text_style.font_families:
                a_sub(rPr, "latin", typeface=text_style.font_families[0])

    @staticmethod
    def _is_node_rtl(node: TextNode) -> bool:
        """Detect if a text node should use RTL paragraph direction."""
        attrs = getattr(node, "attributes", {}) or {}
        styles = getattr(node, "styles", {}) or {}
        direction = styles.get("direction") or attrs.get("direction")
        if direction == "rtl":
            return True
        if direction == "ltr":
            return False
        text = node.text_content or ""
        return bool(text) and is_rtl_text(text)

    def _collect_text_segments(
        self,
        node: TextNode,
    ) -> list[tuple[str, TextStyle | None, FillStyle | None, StrokeStyle | None, bool]]:
        segments: list[
            tuple[str, TextStyle | None, FillStyle | None, StrokeStyle | None, bool]
        ] = []

        def visit(
            current,
            inherited_text_style: TextStyle | None,
            inherited_fill_style: FillStyle | None,
            inherited_stroke_style: StrokeStyle | None,
            preserve_space: bool,
        ) -> None:
            text_style = current.text_style or inherited_text_style
            fill_style = current.fill or inherited_fill_style
            stroke_style = current.stroke or inherited_stroke_style
            source = getattr(current, "source", None)
            xml_space = None
            if source is not None:
                xml_space = source.get("{http://www.w3.org/XML/1998/namespace}space")
            node_preserve = preserve_space or (xml_space == "preserve")
            if source is not None:
                text = getattr(source, "text", None)
                if text:
                    segments.append(
                        (text, text_style, fill_style, stroke_style, node_preserve)
                    )
            for child in getattr(current, "children", []) or []:
                visit(child, text_style, fill_style, stroke_style, node_preserve)
                child_source = getattr(child, "source", None)
                tail = (
                    getattr(child_source, "tail", None)
                    if child_source is not None
                    else None
                )
                if tail:
                    segments.append(
                        (tail, text_style, fill_style, stroke_style, node_preserve)
                    )

        visit(node, node.text_style, node.fill, node.stroke, False)

        if not segments and node.text_content:
            segments.append(
                (node.text_content, node.text_style, node.fill, node.stroke, False)
            )

        return segments

    @staticmethod
    def _normalize_text_segment(
        text: str | None, *, preserve_space: bool = False
    ) -> str:
        if not text:
            return ""
        token = text.replace("\r\n", "\n").replace("\r", "\n")
        if preserve_space:
            if token.strip() == "":
                return "\n" if "\n" in token else " "
            return token
        if "\n" in token:
            collapsed = re.sub(r"\s+", " ", token)
            return collapsed.strip()
        if token.strip() == "":
            return " "
        leading_space = token[:1].isspace()
        trailing_space = token[-1:].isspace()
        core = re.sub(r"\s+", " ", token.strip())
        if leading_space:
            core = f" {core}"
        if trailing_space:
            core = f"{core} "
        return core

    def resolve_font(
        self,
        node: TextNode,
        fallback_chain: tuple[str, ...] = (),
    ) -> FontMatch | None:
        """Resolve font for text node using FontService.

        This method queries the FontService (if configured) to find the best
        matching font for the node's text style. It builds a FontQuery from
        the node's font properties and returns a FontMatch with font metadata.

        Web fonts will have their loaded data in match.metadata["font_data"].

        Args:
            node: TextNode with text_style containing font properties
            fallback_chain: Additional fallback families to try

        Returns:
            FontMatch if font service is configured and font is found, None otherwise

        Example:
            >>> match = generator.resolve_font(node, fallback_chain=("Arial",))
            >>> if match and "font_data" in match.metadata:
            ...     # Web font with loaded data
            ...     pass
        """
        if not self._font_service or not node.text_style:
            return None

        # Import here to avoid circular dependency
        from svg2ooxml.services.fonts.service import FontQuery

        text_style = node.text_style

        # Extract font properties
        primary_family = (
            text_style.font_families[0] if text_style.font_families else "Arial"
        )
        weight = _parse_font_weight(text_style.font_weight)
        style = text_style.font_style or "normal"

        # Build query
        query = FontQuery(
            family=primary_family,
            weight=weight,
            style=style,
            fallback_chain=fallback_chain,
        )

        # Resolve via service
        return self._font_service.find_font(query)

    def embed_font(
        self,
        node: TextNode,
        match: FontMatch,
    ) -> FontEmbeddingResult | None:
        """Embed font using FontEmbeddingEngine.

        This method creates a subsetted font containing only the glyphs needed
        for the node's text content. For web fonts, it passes through the loaded
        font data from match.metadata["font_data"].

        Args:
            node: TextNode with text_content (characters to include in subset)
            match: FontMatch from resolve_font() with path and metadata

        Returns:
            FontEmbeddingResult with subsetted font data, None if embedding fails

        Example:
            >>> match = generator.resolve_font(node)
            >>> result = generator.embed_font(node, match)
            >>> if result:
            ...     font_data = result.packaging_metadata.get("font_data")
            ...     # Use font_data for PowerPoint packaging
        """
        if not self._embedding_engine:
            return None

        # Import here to avoid circular dependency
        from svg2ooxml.services.fonts.embedding import FontEmbeddingRequest

        # Collect characters from text content
        characters = set(node.text_content or "")
        if not characters:
            return None

        # Build embedding request metadata
        metadata: dict[str, object] = {}
        if "font_data" in match.metadata:
            # Web font: pass through loaded data
            metadata["font_data"] = match.metadata["font_data"]

        # Create embedding request
        request = FontEmbeddingRequest(
            font_path=match.path or "unknown",
            characters=tuple(characters),
            preserve_hinting=True,
            subset_strategy="glyph",
            metadata=metadata,
        )

        # Subset font (embedding engine uses font_data if present)
        return self._embedding_engine.subset_font(request)

    def _resolve_gradient_fill(
        self,
        reference: PaintReference | None,
    ) -> etree._Element | None:
        """Resolve a PaintReference to a DrawingML gradient fill element.

        Uses the paint_resolver callback (if configured) to convert a
        PaintReference into an IR Paint, then builds the corresponding
        <a:gradFill> element.

        Args:
            reference: PaintReference with href to gradient/pattern definition

        Returns:
            <a:gradFill> lxml Element, or None if not resolvable
        """
        if reference is None or self._paint_resolver is None:
            return None

        paint = self._paint_resolver(reference)
        if paint is None:
            return None

        from svg2ooxml.ir.paint import LinearGradientPaint, RadialGradientPaint

        if isinstance(paint, LinearGradientPaint):
            from svg2ooxml.drawingml.paint_runtime import (
                _linear_gradient_to_fill_elem,
            )

            return _linear_gradient_to_fill_elem(paint)

        if isinstance(paint, RadialGradientPaint):
            from svg2ooxml.drawingml.paint_runtime import (
                _radial_gradient_to_fill_elem,
            )

            return _radial_gradient_to_fill_elem(paint)

        return None


__all__ = [
    "DrawingMLTextGenerator",
    "DRAWINGML_HUNDREDTHS_PER_POINT",
]
