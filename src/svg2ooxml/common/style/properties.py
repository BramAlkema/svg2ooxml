"""CSS property value conversion helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from svg2ooxml.color.adapters import (
    css_color_to_hex,
    hex_to_rgba_tuple,
    rgba_tuple_to_hex,
)
from svg2ooxml.common.conversions.opacity import parse_opacity
from svg2ooxml.common.style.css_math import (
    CSSMathContext,
    CSSMathError,
    evaluate_calc_string,
)
from svg2ooxml.common.units import UnitConverter
from svg2ooxml.common.units.lengths import resolve_length_px

if TYPE_CHECKING:
    from svg2ooxml.common.style.model import StyleContext
    from svg2ooxml.core.parser.units import UnitConverter


def strip_quotes(value: str) -> str:
    return value.strip("\"'")


def normalize_font_weight(value: str) -> str:
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


def normalize_text_anchor(value: str) -> str:
    return value.strip().lower()


def parse_font_size_token(
    value: str,
    base_pt: float,
    *,
    unitless_scale: float,
) -> float:
    token = value.strip().lower()
    if token.startswith("calc("):
        resolved = _parse_calc_font_size_pt(token, base_pt)
        if resolved is not None:
            return resolved
        return base_pt
    try:
        if token.endswith("px"):
            return float(token[:-2]) * 0.75
        if token.endswith("pt"):
            return float(token[:-2])
        if token.endswith("em"):
            return float(token[:-2]) * base_pt
        if token.endswith("%"):
            return base_pt * float(token[:-1]) / 100.0
        return float(token) * unitless_scale
    except ValueError:
        return base_pt


def _parse_calc_font_size_pt(token: str, base_pt: float) -> float | None:
    converter = UnitConverter()
    base_px = base_pt / 0.75
    conversion = converter.create_context(
        width=0.0,
        height=0.0,
        font_size=base_px,
        root_font_size=base_px,
    )
    context = CSSMathContext(
        conversion_context=conversion,
        unit_converter=converter,
        axis="font-size",
        percentage_basis="length",
    )
    try:
        result = evaluate_calc_string(token, context=context)
        if result.kind == "number":
            return None
        return result.as_length_px(context) * 0.75
    except (CSSMathError, ValueError, ZeroDivisionError):
        return None


def hex_to_rgba(color: str) -> tuple[float, float, float, float]:
    return hex_to_rgba_tuple(color, default=(0.0, 0.0, 0.0, 1.0)) or (
        0.0,
        0.0,
        0.0,
        1.0,
    )


def rgba_to_hex(value: tuple[float, float, float, float]) -> str:
    return rgba_tuple_to_hex(value, prefix="#")


def resolve_color_token(token: str, current_hex: str) -> str:
    stripped = token.strip()
    if not stripped:
        return current_hex
    if stripped.lower() == "none":
        return current_hex
    if stripped.startswith("url("):
        return stripped

    return css_color_to_hex(
        stripped,
        current_color=hex_to_rgba(current_hex),
        default=current_hex,
        prefix="#",
    )


def length_to_px(
    unit_converter: UnitConverter,
    value: str | None,
    context: StyleContext | None,
    *,
    axis: str = "x",
) -> float:
    if value is None:
        return 0.0
    token = value.strip()
    if not token:
        return 0.0

    conversion = context.conversion if context is not None else None
    return resolve_length_px(
        token,
        conversion,
        axis=axis,
        unit_converter=unit_converter,
    )


def parse_style_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    return parse_opacity(value, default)


__all__ = [
    "hex_to_rgba",
    "length_to_px",
    "normalize_font_weight",
    "normalize_text_anchor",
    "parse_font_size_token",
    "parse_style_float",
    "resolve_color_token",
    "rgba_to_hex",
    "strip_quotes",
]
