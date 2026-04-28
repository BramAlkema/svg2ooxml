"""Text segment collection for resvg DrawingML text generation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from svg2ooxml.core.ir.text.layout import normalize_text_segment

if TYPE_CHECKING:
    from svg2ooxml.core.resvg.painting.paint import FillStyle, StrokeStyle, TextStyle
    from svg2ooxml.core.resvg.usvg_tree import TextNode

TextSegment = tuple[
    str,
    "TextStyle | None",
    "FillStyle | None",
    "StrokeStyle | None",
    bool,
]


def collect_text_segments(node: TextNode) -> list[TextSegment]:
    """Collect inherited text/fill/stroke style segments from a resvg text node."""
    segments: list[TextSegment] = []

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


__all__ = ["TextSegment", "collect_text_segments", "normalize_text_segment"]
