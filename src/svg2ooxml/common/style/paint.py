"""Paint style application for SVG CSS properties."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lxml import etree

from svg2ooxml.common.style.cascade import parse_inline_declarations
from svg2ooxml.common.style.model import CSSDeclaration, CSSOrigin, StyleContext
from svg2ooxml.common.style.properties import (
    length_to_px,
    parse_style_float,
    resolve_color_token,
)
from svg2ooxml.common.style.text import DEFAULT_FILL

if TYPE_CHECKING:
    from svg2ooxml.core.parser.units import UnitConverter

DEFAULT_PAINT_STYLE: dict[str, Any] = {
    "color": DEFAULT_FILL,
    "fill": DEFAULT_FILL,
    "fill_opacity": 1.0,
    "stroke": None,
    "stroke_opacity": 1.0,
    "stroke_width_px": 1.0,
    "opacity": 1.0,
}


@dataclass
class PaintApplication:
    style: dict[str, Any]
    importance: dict[str, bool]
    origin: dict[str, CSSOrigin]

    def current_color(self) -> str:
        color = self.style.get("color")
        if isinstance(color, str):
            return color
        return DEFAULT_FILL

    def apply_color(
        self,
        value: str | None,
        importance_flag: bool = False,
        origin: CSSOrigin = CSSOrigin.AUTHOR,
    ) -> None:
        if value is None:
            return
        token = value.strip()
        if not token:
            return
        self.style["color"] = resolve_color_token(token, self.current_color())
        self.importance["color"] = importance_flag
        self.origin["color"] = origin

    def apply_fill(
        self,
        value: str | None,
        importance_flag: bool = False,
        origin: CSSOrigin = CSSOrigin.AUTHOR,
    ) -> None:
        if value is None:
            return
        token = value.strip()
        if not token:
            return
        if token.lower() == "none":
            self.style["fill"] = None
        elif token.startswith("url("):
            self.style["fill"] = token
        else:
            self.style["fill"] = resolve_color_token(token, self.current_color())
        self.importance["fill"] = importance_flag
        self.origin["fill"] = origin

    def apply_stroke(
        self,
        value: str | None,
        importance_flag: bool = False,
        origin: CSSOrigin = CSSOrigin.AUTHOR,
    ) -> None:
        if value is None:
            return
        token = value.strip()
        if not token:
            return
        if token.lower() == "none":
            self.style["stroke"] = None
        elif token.startswith("url("):
            self.style["stroke"] = token
        else:
            self.style["stroke"] = resolve_color_token(token, self.current_color())
        self.importance["stroke"] = importance_flag
        self.origin["stroke"] = origin


def default_paint_style() -> dict[str, Any]:
    return dict(DEFAULT_PAINT_STYLE)


def compute_paint_style(
    element: etree._Element,
    *,
    context: StyleContext | None = None,
    parent_style: dict[str, Any] | None = None,
    stylesheet_declarations: list[CSSDeclaration] | None = None,
    unit_converter: UnitConverter,
) -> dict[str, Any]:
    style = dict(parent_style) if parent_style else default_paint_style()
    app = PaintApplication(style=style, importance={}, origin={})
    skip_stylesheet = element.get("data-svg2ooxml-use-clone") == "true"

    app.apply_color(element.get("color"), False, CSSOrigin.PRESENTATION_ATTR)
    app.apply_fill(element.get("fill"), False, CSSOrigin.PRESENTATION_ATTR)
    app.apply_stroke(element.get("stroke"), False, CSSOrigin.PRESENTATION_ATTR)

    fill_opacity = element.get("fill-opacity")
    if fill_opacity is not None:
        set_float_property(app, "fill_opacity", "fill-opacity", fill_opacity, CSSOrigin.PRESENTATION_ATTR)

    stroke_opacity = element.get("stroke-opacity")
    if stroke_opacity is not None:
        set_float_property(app, "stroke_opacity", "stroke-opacity", stroke_opacity, CSSOrigin.PRESENTATION_ATTR)

    stroke_width = element.get("stroke-width")
    if stroke_width is not None:
        set_stroke_width(app, stroke_width, context, unit_converter, CSSOrigin.PRESENTATION_ATTR)

    opacity = element.get("opacity")
    if opacity is not None:
        set_float_property(app, "opacity", "opacity", opacity, CSSOrigin.PRESENTATION_ATTR)

    if not skip_stylesheet:
        apply_stylesheet_paints(
            stylesheet_declarations or [],
            apply_color=app.apply_color,
            apply_fill=app.apply_fill,
            apply_stroke=app.apply_stroke,
            style=style,
            context=context,
            unit_converter=unit_converter,
            importance_map=app.importance,
            origin_map=app.origin,
        )

    inline = element.get("style")
    if inline:
        for name, value, important in parse_inline_declarations(inline):
            if app.importance.get(name, False) and not important:
                continue

            if name == "color":
                app.apply_color(value, important, CSSOrigin.INLINE)
            elif name == "fill":
                app.apply_fill(value, important, CSSOrigin.INLINE)
            elif name == "fill-opacity":
                set_float_property(app, "fill_opacity", "fill-opacity", value, CSSOrigin.INLINE, important)
            elif name == "stroke":
                app.apply_stroke(value, important, CSSOrigin.INLINE)
            elif name == "stroke-opacity":
                set_float_property(app, "stroke_opacity", "stroke-opacity", value, CSSOrigin.INLINE, important)
            elif name == "stroke-width":
                set_stroke_width(app, value, context, unit_converter, CSSOrigin.INLINE, important)
            elif name == "opacity":
                set_float_property(app, "opacity", "opacity", value, CSSOrigin.INLINE, important)

    return style


def apply_stylesheet_paints(
    declarations: list[CSSDeclaration],
    *,
    apply_color,
    apply_fill,
    apply_stroke,
    style: dict[str, Any],
    context: StyleContext | None,
    unit_converter: UnitConverter,
    importance_map: dict[str, bool] | None = None,
    origin_map: dict[str, CSSOrigin] | None = None,
) -> tuple[dict[str, bool], dict[str, CSSOrigin]]:
    applied_importance = importance_map if importance_map is not None else {}
    applied_origin = origin_map if origin_map is not None else {}
    app = PaintApplication(style=style, importance=applied_importance, origin=applied_origin)

    for decl in declarations:
        name = decl.name
        value = decl.value

        if name == "color":
            apply_color(value, decl.important, decl.origin)
        elif name == "fill":
            apply_fill(value, decl.important, decl.origin)
        elif name == "fill-opacity":
            set_float_property(app, "fill_opacity", "fill-opacity", value, decl.origin, decl.important)
        elif name == "stroke":
            apply_stroke(value, decl.important, decl.origin)
        elif name == "stroke-opacity":
            set_float_property(app, "stroke_opacity", "stroke-opacity", value, decl.origin, decl.important)
        elif name == "stroke-width":
            set_stroke_width(app, value, context, unit_converter, decl.origin, decl.important)
        elif name == "opacity":
            set_float_property(app, "opacity", "opacity", value, decl.origin, decl.important)

    return applied_importance, applied_origin


def set_float_property(
    app: PaintApplication,
    style_key: str,
    css_name: str,
    value: str | None,
    origin: CSSOrigin,
    importance_flag: bool = False,
) -> None:
    app.style[style_key] = parse_style_float(value, default=app.style.get(style_key, 1.0))
    app.importance[css_name] = importance_flag
    app.origin[css_name] = origin


def set_stroke_width(
    app: PaintApplication,
    value: str | None,
    context: StyleContext | None,
    unit_converter: UnitConverter,
    origin: CSSOrigin,
    importance_flag: bool = False,
) -> None:
    app.style["stroke_width_px"] = length_to_px(unit_converter, value, context, axis="x")
    app.importance["stroke-width"] = importance_flag
    app.origin["stroke-width"] = origin


__all__ = [
    "DEFAULT_PAINT_STYLE",
    "PaintApplication",
    "apply_stylesheet_paints",
    "compute_paint_style",
    "default_paint_style",
]
