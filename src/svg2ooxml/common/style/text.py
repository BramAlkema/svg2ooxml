"""Text style application for SVG CSS properties."""

from __future__ import annotations

from typing import Any

from lxml import etree

from svg2ooxml.common.math_utils import coerce_positive_float
from svg2ooxml.common.style.cascade import parse_inline_declarations
from svg2ooxml.common.style.model import (
    CSSDeclaration,
    CSSOrigin,
    PropertyDescriptor,
    StyleContext,
)
from svg2ooxml.common.style.properties import (
    normalize_font_weight,
    normalize_text_anchor,
    parse_font_size_token,
    resolve_color_token,
    strip_quotes,
)

DEFAULT_FONT_SIZE_PT = 12.0
DEFAULT_FILL = "#000000"

TEXT_DEFAULTS: dict[str, Any] = {
    "font_family": "Arial",
    "font_size_pt": DEFAULT_FONT_SIZE_PT,
    "font_weight": "normal",
    "font_style": "normal",
    "text_decoration": "none",
    "text_anchor": "start",
    "color": DEFAULT_FILL,
    "fill": DEFAULT_FILL,
}

TEXT_ATTRIBUTE_MAP: dict[str, PropertyDescriptor] = {
    "font-family": PropertyDescriptor("font_family", strip_quotes),
    "font-size": PropertyDescriptor("font_size_pt", str.strip),
    "font-weight": PropertyDescriptor("font_weight", normalize_font_weight),
    "font-style": PropertyDescriptor("font_style", str.strip),
    "text-decoration": PropertyDescriptor("text_decoration", str.strip),
    "text-anchor": PropertyDescriptor("text_anchor", normalize_text_anchor),
    "color": PropertyDescriptor("color", str.strip),
    "fill": PropertyDescriptor("fill", str.strip),
    "fill-opacity": PropertyDescriptor("fill_opacity", str.strip),
    "stroke": PropertyDescriptor("stroke", str.strip),
    "stroke-width": PropertyDescriptor("stroke_width", str.strip),
    "stroke-opacity": PropertyDescriptor("stroke_opacity", str.strip),
}


def default_text_style() -> dict[str, Any]:
    return dict(TEXT_DEFAULTS)


def compute_text_style(
    element: etree._Element,
    *,
    context: StyleContext | None = None,
    parent_style: dict[str, Any] | None = None,
    stylesheet_declarations: list[CSSDeclaration] | None = None,
    unitless_font_size_scale: float,
) -> dict[str, Any]:
    style = dict(parent_style) if parent_style else default_text_style()
    importance: dict[str, bool] = {}
    origin_level: dict[str, CSSOrigin] = {}
    skip_stylesheet = element.get("data-svg2ooxml-use-clone") == "true"

    for attr, descriptor in TEXT_ATTRIBUTE_MAP.items():
        raw = element.get(attr)
        if raw is None:
            continue
        apply_text_property(
            style,
            descriptor,
            raw,
            context,
            unitless_font_size_scale=unitless_font_size_scale,
        )
        importance[attr] = False
        origin_level[attr] = CSSOrigin.PRESENTATION_ATTR

    if not skip_stylesheet:
        importance, origin_level = apply_stylesheet_text(
            stylesheet_declarations or [],
            style=style,
            context=context,
            importance_map=importance,
            origin_map=origin_level,
            unitless_font_size_scale=unitless_font_size_scale,
        )

    inline = element.get("style")
    if inline:
        for name, value, important in parse_inline_declarations(inline):
            descriptor = TEXT_ATTRIBUTE_MAP.get(name)
            if descriptor is None or value is None:
                continue
            if importance.get(name, False) and not important:
                continue

            apply_text_property(
                style,
                descriptor,
                value,
                context,
                unitless_font_size_scale=unitless_font_size_scale,
            )
            importance[name] = important
            origin_level[name] = CSSOrigin.INLINE

    return style


def apply_stylesheet_text(
    declarations: list[CSSDeclaration],
    *,
    style: dict[str, Any],
    context: StyleContext | None,
    importance_map: dict[str, bool] | None = None,
    origin_map: dict[str, CSSOrigin] | None = None,
    unitless_font_size_scale: float,
) -> tuple[dict[str, bool], dict[str, CSSOrigin]]:
    applied_importance = importance_map if importance_map is not None else {}
    applied_origin = origin_map if origin_map is not None else {}

    for decl in declarations:
        descriptor = TEXT_ATTRIBUTE_MAP.get(decl.name)
        if descriptor is None:
            continue

        apply_text_property(
            style,
            descriptor,
            decl.value,
            context,
            unitless_font_size_scale=unitless_font_size_scale,
        )
        applied_importance[decl.name] = decl.important
        applied_origin[decl.name] = decl.origin

    return applied_importance, applied_origin


def apply_text_property(
    style: dict[str, Any],
    descriptor: PropertyDescriptor,
    raw_value: str,
    context: StyleContext | None,
    *,
    unitless_font_size_scale: float,
) -> None:
    del context
    try:
        value = descriptor.parser(raw_value)
    except Exception:  # pragma: no cover - defensive fallback
        return

    if descriptor.key == "font_size_pt":
        base = coerce_positive_float(
            style.get("font_size_pt"),
            DEFAULT_FONT_SIZE_PT,
        )
        style["font_size_pt"] = parse_font_size_token(
            value,
            base,
            unitless_scale=unitless_font_size_scale,
        )
    elif descriptor.key == "color":
        current = style.get("color", DEFAULT_FILL)
        style["color"] = resolve_color_token(
            value,
            current if isinstance(current, str) else DEFAULT_FILL,
        )
    elif descriptor.key == "fill":
        current = style.get("color", DEFAULT_FILL)
        style["fill"] = resolve_color_token(
            value,
            current if isinstance(current, str) else DEFAULT_FILL,
        )
    else:
        style[descriptor.key] = value


__all__ = [
    "DEFAULT_FILL",
    "DEFAULT_FONT_SIZE_PT",
    "TEXT_ATTRIBUTE_MAP",
    "TEXT_DEFAULTS",
    "apply_stylesheet_text",
    "apply_text_property",
    "compute_text_style",
    "default_text_style",
]
