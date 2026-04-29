"""Contextual SVG/CSS length resolution helpers."""

from __future__ import annotations

import math

from svg2ooxml.common.style.css_math import (
    CSSMathContext,
    CSSMathError,
    evaluate_calc_string,
)
from svg2ooxml.common.units.conversion import ConversionContext, UnitConverter

_DEFAULT_CONVERTER = UnitConverter()


def parse_number_or_percent(value: object, default: float = 0.0) -> float:
    """Parse a bare SVG number or percent as a fraction."""

    if value is None:
        return default
    token = str(value).strip()
    if not token:
        return default
    if token.lower().startswith("calc("):
        try:
            result = evaluate_calc_string(token)
        except (CSSMathError, ZeroDivisionError):
            return default
        if result.kind == "percentage":
            return _finite_or_default(result.value / 100.0, default)
        if result.kind == "number":
            return _finite_or_default(result.value, default)
        return default
    try:
        if token.endswith("%"):
            return _finite_or_default(float(token[:-1]) / 100.0, default)
        return _finite_or_default(float(token), default)
    except (TypeError, ValueError):
        return default


def parse_number(value: object, default: float = 0.0) -> float:
    """Parse a bare SVG/CSS number, including number-only ``calc()`` values."""

    if value is None:
        return default
    token = str(value).strip()
    if not token:
        return default
    if token.lower().startswith("calc("):
        try:
            result = evaluate_calc_string(token)
        except (CSSMathError, ZeroDivisionError):
            return default
        return _finite_or_default(result.value, default) if result.kind == "number" else default
    try:
        return _finite_or_default(float(token), default)
    except (TypeError, ValueError):
        return default


def parse_percentage(value: object, default: float = 0.0) -> float:
    """Parse a percent token as a fraction, including percent-only ``calc()``."""

    if value is None:
        return default
    token = str(value).strip()
    if not token:
        return default
    if token.lower().startswith("calc("):
        try:
            result = evaluate_calc_string(token)
        except (CSSMathError, ZeroDivisionError):
            return default
        return (
            _finite_or_default(result.value / 100.0, default)
            if result.kind == "percentage"
            else default
        )
    if not token.endswith("%"):
        return default
    try:
        return _finite_or_default(float(token[:-1]) / 100.0, default)
    except (TypeError, ValueError):
        return default


def _finite_or_default(value: float, default: float) -> float:
    return value if math.isfinite(value) else default


def parse_number_list(value: str | None) -> list[float]:
    """Parse a comma/space-separated list of SVG/CSS numbers."""

    if not value:
        return []
    values: list[float] = []
    for token in split_length_list(value):
        number = parse_number(token, float("nan"))
        if number == number:
            values.append(number)
    return values


def resolve_length_px(
    value: object,
    context: ConversionContext | None,
    *,
    axis: str,
    default: float = 0.0,
    unit_converter: UnitConverter | None = None,
    fallback_unit: str = "px",
) -> float:
    """Resolve an SVG/CSS length to px, returning *default* on invalid input."""

    if value is None:
        return default
    token = str(value).strip()
    if not token:
        return default
    converter = unit_converter or _DEFAULT_CONVERTER
    try:
        return resolve_length_px_required(
            token,
            context,
            axis=axis,
            unit_converter=converter,
            fallback_unit=fallback_unit,
        )
    except (AttributeError, TypeError, ValueError, ZeroDivisionError):
        return default


def resolve_length_px_required(
    value: str,
    context: ConversionContext | None,
    *,
    axis: str,
    unit_converter: UnitConverter | None = None,
    fallback_unit: str = "px",
) -> float:
    """Resolve an SVG/CSS length to px or raise on invalid input."""

    token = value.strip()
    converter = unit_converter or _DEFAULT_CONVERTER
    if token.lower().startswith("calc("):
        math_context = CSSMathContext(
            conversion_context=context,
            unit_converter=converter,
            axis=axis,
            fallback_unit=fallback_unit,
            percentage_basis="length",
        )
        result = evaluate_calc_string(token, context=math_context)
        return result.as_length_px(math_context)
    return converter.to_px(token, context, axis=axis, fallback_unit=fallback_unit)


def resolve_length_list_px(
    value: str | None,
    context: ConversionContext | None,
    *,
    axis: str,
    unit_converter: UnitConverter | None = None,
    fallback_unit: str = "px",
) -> list[float]:
    """Resolve a comma/space-separated SVG length list to px values."""

    if not value:
        return []
    return [
        resolve_length_px(
            token,
            context,
            axis=axis,
            unit_converter=unit_converter,
            fallback_unit=fallback_unit,
        )
        for token in split_length_list(value)
    ]


def resolve_user_length_px(
    value: object,
    default: float,
    viewport_length: float,
    *,
    axis: str = "x",
    unit_converter: UnitConverter | None = None,
) -> float:
    """Resolve a user-space filter/viewport length with a single reference axis."""

    converter = unit_converter or _DEFAULT_CONVERTER
    context = converter.create_context(
        width=viewport_length,
        height=viewport_length,
        parent_width=viewport_length,
        parent_height=viewport_length,
        viewport_width=viewport_length,
        viewport_height=viewport_length,
    )
    return resolve_length_px(
        value,
        context,
        axis=axis,
        default=default,
        unit_converter=converter,
    )


def split_length_list(value: str) -> list[str]:
    """Split a length list without breaking whitespace inside ``calc()``."""

    tokens: list[str] = []
    current: list[str] = []
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
            current.append(char)
            continue
        if char == ")":
            depth = max(depth - 1, 0)
            current.append(char)
            continue
        if depth == 0 and (char == "," or char.isspace()):
            if current:
                tokens.append("".join(current).strip())
                current = []
            continue
        current.append(char)
    if current:
        tokens.append("".join(current).strip())
    return [token for token in tokens if token]


__all__ = [
    "parse_number",
    "parse_number_list",
    "parse_number_or_percent",
    "parse_percentage",
    "resolve_length_list_px",
    "resolve_length_px",
    "resolve_length_px_required",
    "resolve_user_length_px",
    "split_length_list",
]
