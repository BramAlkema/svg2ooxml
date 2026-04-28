"""Presentation style resolution for parser-to-usvg conversion."""

from __future__ import annotations

from .painting.paint import (
    FillStyle,
    StrokeStyle,
    TextStyle,
    resolve_fill,
    resolve_stroke,
    resolve_text_style,
)
from .parser.presentation import Presentation
from .usvg_nodes import BaseNode

_DEFAULT_TEXT_FONT_SIZE_PT = 12.0


def resolve_node_fill(
    presentation: Presentation,
    attributes: dict[str, str],
    styles: dict[str, str],
) -> FillStyle | None:
    raw_fill = styles.get("fill") if "fill" in styles else attributes.get("fill")
    explicit_no_fill = bool(raw_fill) and raw_fill.strip().lower() in {
        "none",
        "transparent",
    }
    fill_style = resolve_fill(
        presentation.fill,
        presentation.fill_opacity,
        presentation.opacity,
    )
    if (
        fill_style.color is None
        and fill_style.reference is None
        and not explicit_no_fill
    ):
        return None
    return fill_style


def resolve_node_stroke(
    presentation: Presentation,
    attributes: dict[str, str],
    styles: dict[str, str],
) -> StrokeStyle | None:
    raw_stroke = (
        styles.get("stroke") if "stroke" in styles else attributes.get("stroke")
    )
    explicit_no_stroke = bool(raw_stroke) and raw_stroke.strip().lower() in {
        "none",
        "transparent",
    }
    stroke_style = resolve_stroke(
        presentation.stroke,
        presentation.stroke_width,
        presentation.stroke_opacity,
        presentation.opacity,
        dasharray=presentation.stroke_dasharray,
        dashoffset=presentation.stroke_dashoffset,
        linecap=presentation.stroke_linecap,
        linejoin=presentation.stroke_linejoin,
        miterlimit=presentation.stroke_miterlimit,
    )
    if (
        stroke_style.color is None
        and stroke_style.reference is None
        and stroke_style.width is None
        and not explicit_no_stroke
    ):
        return None
    return stroke_style


def resolve_node_text_style(
    presentation: Presentation,
    parent: BaseNode | None,
) -> TextStyle | None:
    presentation_font_size = presentation.font_size
    if presentation.font_size_scale is not None:
        parent_font_size = (
            parent.text_style.font_size
            if parent is not None
            and parent.text_style is not None
            and parent.text_style.font_size is not None
            else _DEFAULT_TEXT_FONT_SIZE_PT
        )
        presentation_font_size = parent_font_size * presentation.font_size_scale

    resolved_text_style = resolve_text_style(
        presentation.font_family,
        presentation_font_size,
        presentation.font_style,
        presentation.font_weight,
        text_decoration=getattr(presentation, "text_decoration", None),
        letter_spacing=getattr(presentation, "letter_spacing", None),
    )
    if (
        not resolved_text_style.font_families
        and resolved_text_style.font_size is None
        and resolved_text_style.font_style is None
        and resolved_text_style.font_weight is None
    ):
        return None
    return resolved_text_style
