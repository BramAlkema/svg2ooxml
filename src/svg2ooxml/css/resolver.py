"""CSS style resolver with tinycss2-backed parsing."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import tinycss2

from svg2ooxml.parser.colors import parse_color
from svg2ooxml.parser.units import ConversionContext, UnitConverter

PropertyHandler = Callable[[str], object]

_DEFAULT_FONT_SIZE_PT = 12.0
_DEFAULT_FILL = "#000000"


def _strip_quotes(value: str) -> str:
    return value.strip('"\'' )


def _normalize_font_weight(value: str) -> str:
    token = value.strip().lower()
    mapping = {
        "100": "lighter",
        "200": "lighter",
        "300": "light",
        "400": "normal",
        "500": "normal",
        "600": "semibold",
        "700": "bold",
        "800": "bolder",
        "900": "bolder",
    }
    return mapping.get(token, token)


def _parse_font_size_token(value: str, base_pt: float) -> float:
    token = value.strip().lower()
    try:
        if token.endswith("px"):
            return float(token[:-2]) * 0.75
        if token.endswith("pt"):
            return float(token[:-2])
        if token.endswith("em"):
            return float(token[:-2]) * base_pt
        if token.endswith("%"):
            return base_pt * float(token[:-1]) / 100.0
        return float(token)
    except ValueError:
        return base_pt


def _hex_to_rgba(color: str) -> tuple[float, float, float, float]:
    token = color.lstrip("#")
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    if len(token) != 6:
        return (0.0, 0.0, 0.0, 1.0)
    r = int(token[0:2], 16) / 255.0
    g = int(token[2:4], 16) / 255.0
    b = int(token[4:6], 16) / 255.0
    return (r, g, b, 1.0)


def _rgba_to_hex(value: tuple[float, float, float, float]) -> str:
    r, g, b, _ = value
    return "#{:02X}{:02X}{:02X}".format(
        max(0, min(255, int(round(r * 255)))),
        max(0, min(255, int(round(g * 255)))),
        max(0, min(255, int(round(b * 255)))),
    )


@dataclass(frozen=True)
class PropertyDescriptor:
    """Maps CSS property names to resolver keys and parsers."""

    key: str
    parser: PropertyHandler


@dataclass(frozen=True)
class StyleContext:
    """Viewport-aware context for CSS evaluation."""

    conversion: ConversionContext
    viewport_width: float
    viewport_height: float


class StyleResolver:
    """Resolve SVG style attributes and inline CSS using tinycss2."""

    _TEXT_DEFAULTS: dict[str, Any] = {
        "font_family": "Arial",
        "font_size_pt": _DEFAULT_FONT_SIZE_PT,
        "font_weight": "normal",
        "font_style": "normal",
        "text_decoration": "none",
        "fill": _DEFAULT_FILL,
    }

    _TEXT_ATTRIBUTE_MAP: dict[str, PropertyDescriptor] = {
        "font-family": PropertyDescriptor("font_family", _strip_quotes),
        "font-size": PropertyDescriptor("font_size_pt", str.strip),
        "font-weight": PropertyDescriptor("font_weight", _normalize_font_weight),
        "font-style": PropertyDescriptor("font_style", str.strip),
        "text-decoration": PropertyDescriptor("text_decoration", str.strip),
        "fill": PropertyDescriptor("fill", str.strip),
    }

    _TEXT_CSS_MAP = _TEXT_ATTRIBUTE_MAP

    def __init__(self, unit_converter: UnitConverter | None = None) -> None:
        self._unit_converter = unit_converter or UnitConverter()

    # ------------------------------------------------------------------ #
    # Text styling                                                       #
    # ------------------------------------------------------------------ #

    def default_text_style(self) -> dict[str, Any]:
        return dict(self._TEXT_DEFAULTS)

    def compute_text_style(
        self,
        element,
        context: StyleContext | None = None,
        parent_style: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        style = dict(parent_style) if parent_style else self.default_text_style()

        for attr, descriptor in self._TEXT_ATTRIBUTE_MAP.items():
            raw = element.get(attr)
            if raw is None:
                continue
            self._apply_text_property(style, descriptor, raw, context)

        inline = element.get("style")
        if inline:
            for name, value, _important in self._parse_inline_declarations(inline):
                descriptor = self._TEXT_CSS_MAP.get(name)
                if descriptor and value is not None:
                    self._apply_text_property(style, descriptor, value, context)

        return style

    # ------------------------------------------------------------------ #
    # Presentation styling                                               #
    # ------------------------------------------------------------------ #

    def compute_paint_style(
        self,
        element,
        context: StyleContext | None = None,
        parent_style: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        style = dict(parent_style) if parent_style else {
            "fill": _DEFAULT_FILL,
            "fill_opacity": 1.0,
            "stroke": None,
            "stroke_opacity": 1.0,
            "stroke_width_px": 1.0,
            "opacity": 1.0,
        }

        def current_fill() -> str:
            fill = style.get("fill")
            if isinstance(fill, str):
                return fill
            return _DEFAULT_FILL

        def apply_fill(value: str | None) -> None:
            if value is None:
                return
            token = value.strip()
            if not token:
                return
            if token.lower() == "none":
                style["fill"] = None
                return
            if token.startswith("url("):
                style["fill"] = token
                return
            style["fill"] = self._resolve_color(token, current_fill())

        def apply_stroke(value: str | None) -> None:
            if value is None:
                return
            token = value.strip()
            if not token:
                return
            if token.lower() == "none":
                style["stroke"] = None
                return
            if token.startswith("url("):
                style["stroke"] = token
                return
            style["stroke"] = self._resolve_color(token, style.get("stroke") or _DEFAULT_FILL)

        apply_fill(element.get("fill"))
        apply_stroke(element.get("stroke"))

        fill_opacity = element.get("fill-opacity")
        if fill_opacity is not None:
            style["fill_opacity"] = self._parse_float(fill_opacity, default=style.get("fill_opacity", 1.0))

        stroke_opacity = element.get("stroke-opacity")
        if stroke_opacity is not None:
            style["stroke_opacity"] = self._parse_float(stroke_opacity, default=style.get("stroke_opacity", 1.0))

        stroke_width = element.get("stroke-width")
        if stroke_width is not None:
            style["stroke_width_px"] = self._length_to_px(stroke_width, context, axis="x")

        opacity = element.get("opacity")
        if opacity is not None:
            style["opacity"] = self._parse_float(opacity, default=style.get("opacity", 1.0))

        inline = element.get("style")
        if inline:
            for name, value, _important in self._parse_inline_declarations(inline):
                if name == "fill":
                    apply_fill(value)
                elif name == "fill-opacity":
                    style["fill_opacity"] = self._parse_float(value, default=style.get("fill_opacity", 1.0))
                elif name == "stroke":
                    apply_stroke(value)
                elif name == "stroke-opacity":
                    style["stroke_opacity"] = self._parse_float(value, default=style.get("stroke_opacity", 1.0))
                elif name == "stroke-width":
                    style["stroke_width_px"] = self._length_to_px(value, context, axis="x")
                elif name == "opacity":
                    style["opacity"] = self._parse_float(value, default=style.get("opacity", 1.0))

        return style

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    def _parse_inline_declarations(
        self,
        style_str: str,
    ) -> Iterable[tuple[str, str, bool]]:
        if not style_str:
            return []
        try:
            declarations = tinycss2.parse_declaration_list(
                style_str,
                skip_whitespace=True,
                skip_comments=True,
            )
        except Exception:
            return []

        resolved: list[tuple[str, str, bool]] = []
        for decl in declarations:
            if decl.type != "declaration":
                continue
            name = decl.name.lower()
            value = tinycss2.serialize(decl.value).strip()
            resolved.append((name, value, bool(decl.important)))
        return resolved

    def _apply_text_property(
        self,
        style: dict[str, Any],
        descriptor: PropertyDescriptor,
        raw_value: str,
        context: StyleContext | None,
    ) -> None:
        try:
            value = descriptor.parser(raw_value)
        except Exception:  # pragma: no cover - defensive fallback
            return

        if descriptor.key == "font_size_pt":
            base = float(style.get("font_size_pt", _DEFAULT_FONT_SIZE_PT))
            style["font_size_pt"] = _parse_font_size_token(value, base)
        elif descriptor.key == "fill":
            current = style.get("fill", _DEFAULT_FILL)
            style["fill"] = self._resolve_color(value, current if isinstance(current, str) else _DEFAULT_FILL)
        else:
            style[descriptor.key] = value

    def _resolve_color(self, token: str, current_hex: str) -> str:
        stripped = token.strip()
        if not stripped:
            return current_hex
        if stripped.lower() == "none":
            return current_hex
        if stripped.startswith("url("):
            return stripped
        rgba = parse_color(stripped, current_color=_hex_to_rgba(current_hex))
        if rgba is None:
            return current_hex
        return _rgba_to_hex(rgba)

    def _length_to_px(
        self,
        value: str | None,
        context: StyleContext | None,
        axis: str = "x",
    ) -> float:
        if value is None:
            return 0.0
        token = value.strip()
        if not token:
            return 0.0

        try:
            return float(token)
        except ValueError:
            pass

        if context is not None:
            if token.endswith("%"):
                try:
                    pct = float(token[:-1])
                except ValueError:
                    pct = 0.0
                basis = context.viewport_width if axis == "x" else context.viewport_height
                return basis * (pct / 100.0) if basis is not None else 0.0
            if token.endswith("em"):
                try:
                    return float(token[:-2]) * context.conversion.font_size
                except ValueError:
                    return context.conversion.font_size

        try:
            return self._unit_converter.to_px(token)
        except Exception:
            return 0.0

    @staticmethod
    def _parse_float(value: str | None, default: float) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default


__all__ = ["StyleContext", "StyleResolver"]
