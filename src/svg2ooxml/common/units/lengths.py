"""Contextual SVG/CSS length resolution helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from svg2ooxml.common.units.conversion import ConversionContext, UnitConverter

_NUMBER_RE = re.compile(r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_DEFAULT_CONVERTER = UnitConverter()


def parse_number_or_percent(value: object, default: float = 0.0) -> float:
    """Parse a bare SVG number or percent as a fraction."""

    if value is None:
        return default
    token = str(value).strip()
    if not token:
        return default
    try:
        if token.endswith("%"):
            return float(token[:-1]) / 100.0
        return float(token)
    except (TypeError, ValueError):
        return default


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
    calc_inner = _calc_inner(token)
    if calc_inner is not None:
        result = _CalcParser(
            calc_inner,
            context,
            axis=axis,
            unit_converter=converter,
            fallback_unit=fallback_unit,
        ).parse()
        return result.as_length_px(converter, context, axis=axis, fallback_unit=fallback_unit)
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


def _calc_inner(value: str) -> str | None:
    token = value.strip()
    if not token.lower().startswith("calc(") or not token.endswith(")"):
        return None
    depth = 0
    for index, char in enumerate(token[4:], start=4):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and index != len(token) - 1:
                return None
    return token[5:-1].strip()


@dataclass(frozen=True, slots=True)
class _CalcValue:
    value: float
    kind: Literal["number", "length"]

    def as_length_px(
        self,
        converter: UnitConverter,
        context: ConversionContext | None,
        *,
        axis: str,
        fallback_unit: str,
    ) -> float:
        if self.kind == "length":
            return self.value
        return converter.to_px(
            self.value,
            context,
            axis=axis,
            fallback_unit=fallback_unit,
        )


class _CalcParser:
    def __init__(
        self,
        source: str,
        context: ConversionContext | None,
        *,
        axis: str,
        unit_converter: UnitConverter,
        fallback_unit: str,
    ) -> None:
        self.source = source
        self.context = context
        self.axis = axis
        self.unit_converter = unit_converter
        self.fallback_unit = fallback_unit
        self.index = 0

    def parse(self) -> _CalcValue:
        value = self._expression()
        self._skip_ws()
        if self.index != len(self.source):
            raise ValueError(f"Unexpected calc token {self.source[self.index:]!r}")
        return value

    def _expression(self) -> _CalcValue:
        left = self._term()
        while True:
            self._skip_ws()
            op = self._peek()
            if op not in {"+", "-"}:
                return left
            self.index += 1
            right = self._term()
            left = self._add(left, right, op)

    def _term(self) -> _CalcValue:
        left = self._factor()
        while True:
            self._skip_ws()
            op = self._peek()
            if op not in {"*", "/"}:
                return left
            self.index += 1
            right = self._factor()
            left = self._multiply(left, right, op)

    def _factor(self) -> _CalcValue:
        self._skip_ws()
        op = self._peek()
        if op == "+":
            self.index += 1
            return self._factor()
        if op == "-":
            self.index += 1
            value = self._factor()
            return _CalcValue(-value.value, value.kind)
        if op == "(":
            self.index += 1
            value = self._expression()
            self._skip_ws()
            if self._peek() != ")":
                raise ValueError("Unclosed calc parenthesis")
            self.index += 1
            return value
        return self._number()

    def _number(self) -> _CalcValue:
        match = _NUMBER_RE.match(self.source, self.index)
        if match is None:
            raise ValueError("Expected calc number")
        number_text = match.group(0)
        self.index = match.end()
        unit_start = self.index
        while self.index < len(self.source) and (
            self.source[self.index].isalpha() or self.source[self.index] == "%"
        ):
            self.index += 1
        unit = self.source[unit_start:self.index]
        if unit:
            token = f"{number_text}{unit}"
            return _CalcValue(
                self.unit_converter.to_px(
                    token,
                    self.context,
                    axis=self.axis,
                    fallback_unit=self.fallback_unit,
                ),
                "length",
            )
        return _CalcValue(float(number_text), "number")

    def _add(self, left: _CalcValue, right: _CalcValue, op: str) -> _CalcValue:
        if left.kind == "number" and right.kind == "number":
            delta = right.value if op == "+" else -right.value
            return _CalcValue(left.value + delta, "number")

        left_px = left.as_length_px(
            self.unit_converter,
            self.context,
            axis=self.axis,
            fallback_unit=self.fallback_unit,
        )
        right_px = right.as_length_px(
            self.unit_converter,
            self.context,
            axis=self.axis,
            fallback_unit=self.fallback_unit,
        )
        return _CalcValue(left_px + (right_px if op == "+" else -right_px), "length")

    @staticmethod
    def _multiply(left: _CalcValue, right: _CalcValue, op: str) -> _CalcValue:
        if op == "/":
            if abs(right.value) <= 1e-12:
                raise ZeroDivisionError("division by zero in calc()")
            if right.kind != "number":
                raise ValueError("calc() division by a length is not supported")
            return _CalcValue(left.value / right.value, left.kind)

        if left.kind == "length" and right.kind == "length":
            raise ValueError("calc() cannot multiply two lengths")
        if left.kind == "number" and right.kind == "number":
            return _CalcValue(left.value * right.value, "number")
        return _CalcValue(left.value * right.value, "length")

    def _skip_ws(self) -> None:
        while self.index < len(self.source) and self.source[self.index].isspace():
            self.index += 1

    def _peek(self) -> str | None:
        if self.index >= len(self.source):
            return None
        return self.source[self.index]


__all__ = [
    "parse_number_or_percent",
    "resolve_length_list_px",
    "resolve_length_px",
    "resolve_length_px_required",
    "resolve_user_length_px",
    "split_length_list",
]
