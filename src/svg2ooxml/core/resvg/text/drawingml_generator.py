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

from collections.abc import Callable
from typing import TYPE_CHECKING

from lxml import etree  # For type annotations

# Import centralized unit conversion constants
from svg2ooxml.common.conversions.bidi import is_rtl_text
from svg2ooxml.common.conversions.opacity import opacity_to_ppt
from svg2ooxml.common.units import px_to_emu
from svg2ooxml.core.resvg.text.drawingml_text_fonts import DrawingMLTextFontMixin
from svg2ooxml.core.resvg.text.drawingml_text_paint import DrawingMLTextPaintMixin
from svg2ooxml.core.resvg.text.drawingml_text_properties import (
    DRAWINGML_HUNDREDTHS_PER_POINT,
    _color_to_hex,
    _font_size_pt_to_drawingml,
    _map_font_style,
    _map_font_weight,
)
from svg2ooxml.core.resvg.text.drawingml_text_properties import (
    _parse_font_weight as _parse_font_weight,
)
from svg2ooxml.core.resvg.text.drawingml_text_segments import (
    collect_text_segments,
    normalize_text_segment,
)

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, p_elem, to_string

if TYPE_CHECKING:
    from svg2ooxml.core.resvg.painting.paint import (
        FillStyle,
        PaintReference,
        StrokeStyle,
        TextStyle,
    )
    from svg2ooxml.core.resvg.usvg_tree import TextNode
    from svg2ooxml.ir.paint import Paint
    from svg2ooxml.services.fonts.embedding import (
        FontEmbeddingEngine,
    )
    from svg2ooxml.services.fonts.service import FontService


class DrawingMLTextGenerator(DrawingMLTextFontMixin, DrawingMLTextPaintMixin):
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
        text_scale: float = 1.0,
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
        self._text_scale = float(text_scale) if text_scale > 0.0 else 1.0

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
            stroke_width = float(stroke_style.width) * self._text_scale
            ln = a_sub(rPr, "ln", w=str(round(px_to_emu(stroke_width))))
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
                    size_hundredths = _font_size_pt_to_drawingml(
                        text_style.font_size * self._text_scale
                    )
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
                spc = round(text_style.letter_spacing * self._text_scale * 75)
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

    _collect_text_segments = staticmethod(collect_text_segments)
    _normalize_text_segment = staticmethod(normalize_text_segment)


__all__ = [
    "DrawingMLTextGenerator",
    "DRAWINGML_HUNDREDTHS_PER_POINT",
]
