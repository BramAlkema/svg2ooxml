"""Typed CSS math helpers for ``calc()`` expressions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import tinycss2

from svg2ooxml.common.units.conversion import ConversionContext, UnitConverter

CSSMathKind = Literal["number", "length", "percentage", "length-percentage", "angle", "time"]
PercentageBasis = Literal["preserve", "length"]

_LENGTH_UNITS = {
    "px",
    "in",
    "cm",
    "mm",
    "pt",
    "pc",
    "q",
    "em",
    "ex",
    "ch",
    "rem",
    "font",
    "vw",
    "vh",
    "vmin",
    "vmax",
}
_ABSOLUTE_LENGTH_UNITS = {"px", "in", "cm", "mm", "pt", "pc", "q"}
_ANGLE_UNITS = {"deg", "grad", "rad", "turn"}
_TIME_UNITS = {"s", "ms", "min", "h"}
_ANGLE_TO_DEGREES = {
    "deg": 1.0,
    "grad": 0.9,
    "rad": 180.0 / 3.141592653589793,
    "turn": 360.0,
}
_TIME_TO_SECONDS = {
    "s": 1.0,
    "ms": 0.001,
    "min": 60.0,
    "h": 3600.0,
}


class CSSMathError(ValueError):
    """Raised when a CSS math expression cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class CSSMathContext:
    """Context needed to resolve relative CSS math values."""

    conversion_context: ConversionContext | None = None
    unit_converter: UnitConverter | None = None
    axis: str | None = None
    fallback_unit: str = "px"
    percentage_basis: PercentageBasis = "preserve"

    @property
    def converter(self) -> UnitConverter:
        return self.unit_converter or UnitConverter()


@dataclass(frozen=True, slots=True)
class CSSMathValue:
    """Typed numeric result from a CSS math expression."""

    value: float
    kind: CSSMathKind
    unit: str = ""
    percentage: float = 0.0

    def as_length_px(self, context: CSSMathContext) -> float:
        """Resolve this value as a CSS/SVG length in px."""

        converter = context.converter
        if self.kind == "length":
            if self.unit == "px":
                return self.value
            return converter.to_px(
                self.to_css(),
                context.conversion_context,
                axis=context.axis,
                fallback_unit=context.fallback_unit,
            )
        if self.kind == "percentage":
            return converter.to_px(
                self.to_css(),
                context.conversion_context,
                axis=context.axis,
                fallback_unit=context.fallback_unit,
            )
        if self.kind == "length-percentage":
            length_px = converter.to_px(
                f"{self.value:g}{self.unit}",
                context.conversion_context,
                axis=context.axis,
                fallback_unit=context.fallback_unit,
            )
            percentage_px = converter.to_px(
                f"{self.percentage:g}%",
                context.conversion_context,
                axis=context.axis,
                fallback_unit=context.fallback_unit,
            )
            return length_px + percentage_px
        if self.kind == "number":
            return converter.to_px(
                self.value,
                context.conversion_context,
                axis=context.axis,
                fallback_unit=context.fallback_unit,
            )
        raise CSSMathError(f"Cannot resolve {self.kind} as a length")

    def to_css(self) -> str:
        """Serialize a simple typed value back to CSS syntax."""

        if self.kind == "length-percentage":
            return _serialize_length_percentage(self.percentage, self.value, self.unit)
        suffix = "%" if self.kind == "percentage" else self.unit
        return f"{self.value:g}{suffix}"

    def as_degrees(self) -> float:
        """Resolve this value as degrees."""

        if self.kind == "angle" and self.unit == "deg":
            return self.value
        raise CSSMathError(f"Cannot resolve {self.kind} as an angle")

    def as_seconds(self) -> float:
        """Resolve this value as seconds."""

        if self.kind == "time" and self.unit == "s":
            return self.value
        raise CSSMathError(f"Cannot resolve {self.kind} as time")

    def scaled(self, factor: float) -> CSSMathValue:
        """Return this value multiplied by a scalar."""

        return CSSMathValue(
            self.value * factor,
            self.kind,
            self.unit,
            self.percentage * factor,
        )


def evaluate_calc_string(value: str, context: CSSMathContext | None = None) -> CSSMathValue:
    """Evaluate a string containing exactly one ``calc()`` function."""

    try:
        token = tinycss2.parse_one_component_value(value)
    except Exception as exc:  # pragma: no cover - tinycss2 exception details vary
        raise CSSMathError(f"Invalid CSS value {value!r}") from exc
    if getattr(token, "type", None) != "function" or getattr(token, "lower_name", "") != "calc":
        raise CSSMathError(f"Expected calc() expression, got {value!r}")
    return evaluate_calc_function(token, context=context)


def evaluate_calc_function(token, context: CSSMathContext | None = None) -> CSSMathValue:
    """Evaluate a tinycss2 ``calc()`` function token."""

    if getattr(token, "type", None) != "function" or getattr(token, "lower_name", "") != "calc":
        raise CSSMathError("Expected calc() function token")
    return _CalcTokenParser(
        getattr(token, "arguments", ()),
        context or CSSMathContext(),
    ).parse()


def simplify_calc_functions(value: str) -> str:
    """Fold top-level context-free ``calc()`` functions when units are compatible."""

    try:
        tokens = tinycss2.parse_component_value_list(value)
    except Exception:
        return value

    output: list[str] = []
    for token in tokens:
        if getattr(token, "type", None) == "function" and getattr(token, "lower_name", "") == "calc":
            try:
                output.append(evaluate_calc_function(token).to_css())
            except CSSMathError:
                output.append(tinycss2.serialize([token]))
            continue
        output.append(tinycss2.serialize([token]))
    return "".join(output).strip()


class _CalcTokenParser:
    def __init__(self, tokens, context: CSSMathContext) -> None:
        self.tokens = [
            token
            for token in tokens
            if getattr(token, "type", None) not in {"whitespace", "comment"}
        ]
        self.context = context
        self.index = 0

    def parse(self) -> CSSMathValue:
        value = self._expression()
        if self.index != len(self.tokens):
            raise CSSMathError("Unexpected token in calc()")
        return value

    def _expression(self) -> CSSMathValue:
        left = self._term()
        while self._literal_value() in {"+", "-"}:
            op = self._consume_literal()
            right = self._term()
            left = self._add(left, right, op)
        return left

    def _term(self) -> CSSMathValue:
        left = self._factor()
        while self._literal_value() in {"*", "/"}:
            op = self._consume_literal()
            right = self._factor()
            left = self._multiply(left, right, op)
        return left

    def _factor(self) -> CSSMathValue:
        op = self._literal_value()
        if op == "+":
            self.index += 1
            return self._factor()
        if op == "-":
            self.index += 1
            value = self._factor()
            return value.scaled(-1.0)

        token = self._consume_token()
        token_type = getattr(token, "type", None)
        if token_type == "() block":
            return _CalcTokenParser(token.content, self.context).parse()
        if token_type == "function" and getattr(token, "lower_name", "") == "calc":
            return _CalcTokenParser(token.arguments, self.context).parse()
        if token_type == "number":
            return CSSMathValue(float(token.value), "number")
        if token_type == "percentage":
            return self._percentage(float(token.value))
        if token_type == "dimension":
            return self._dimension(float(token.value), str(token.unit).lower())
        raise CSSMathError("Expected numeric token in calc()")

    def _percentage(self, value: float) -> CSSMathValue:
        if self.context.percentage_basis == "length":
            px_value = self.context.converter.to_px(
                f"{value:g}%",
                self.context.conversion_context,
                axis=self.context.axis,
                fallback_unit=self.context.fallback_unit,
            )
            return CSSMathValue(px_value, "length", "px")
        return CSSMathValue(value, "percentage", "%")

    def _dimension(self, value: float, unit: str) -> CSSMathValue:
        if unit in _LENGTH_UNITS:
            if self.context.conversion_context is not None or unit in _ABSOLUTE_LENGTH_UNITS:
                px_value = self.context.converter.to_px(
                    f"{value:g}{unit}",
                    self.context.conversion_context,
                    axis=self.context.axis,
                    fallback_unit=self.context.fallback_unit,
                )
                return CSSMathValue(px_value, "length", "px")
            return CSSMathValue(value, "length", unit)
        if unit in _ANGLE_UNITS:
            return CSSMathValue(value * _ANGLE_TO_DEGREES[unit], "angle", "deg")
        if unit in _TIME_UNITS:
            return CSSMathValue(value * _TIME_TO_SECONDS[unit], "time", "s")
        raise CSSMathError(f"Unsupported calc() unit {unit!r}")

    def _add(self, left: CSSMathValue, right: CSSMathValue, op: str) -> CSSMathValue:
        if left.kind == right.kind and left.unit == right.unit:
            delta = right.value if op == "+" else -right.value
            percentage_delta = right.percentage if op == "+" else -right.percentage
            return CSSMathValue(
                left.value + delta,
                left.kind,
                left.unit,
                left.percentage + percentage_delta,
            )

        if self.context.conversion_context is not None and {left.kind, right.kind} == {
            "length",
            "number",
        }:
            left_px = left.as_length_px(self.context)
            right_px = right.as_length_px(self.context)
            return CSSMathValue(left_px + (right_px if op == "+" else -right_px), "length", "px")

        if self.context.percentage_basis == "preserve":
            length_percentage = _combine_length_percentage(left, right, op)
            if length_percentage is not None:
                return length_percentage

        raise CSSMathError("Cannot add incompatible calc() value types")

    @staticmethod
    def _multiply(left: CSSMathValue, right: CSSMathValue, op: str) -> CSSMathValue:
        if op == "/":
            if right.kind != "number":
                raise CSSMathError("calc() division by a non-number is not supported")
            if abs(right.value) <= 1e-12:
                raise ZeroDivisionError("division by zero in calc()")
            return left.scaled(1.0 / right.value)

        if left.kind == "number" and right.kind == "number":
            return CSSMathValue(left.value * right.value, "number")
        if left.kind == "number":
            return right.scaled(left.value)
        if right.kind == "number":
            return left.scaled(right.value)
        raise CSSMathError("calc() cannot multiply two typed values")

    def _consume_token(self):
        if self.index >= len(self.tokens):
            raise CSSMathError("Unexpected end of calc()")
        token = self.tokens[self.index]
        self.index += 1
        return token

    def _literal_value(self) -> str | None:
        if self.index >= len(self.tokens):
            return None
        token = self.tokens[self.index]
        if getattr(token, "type", None) != "literal":
            return None
        return str(token.value)

    def _consume_literal(self) -> str:
        value = self._literal_value()
        if value is None:
            raise CSSMathError("Expected calc() operator")
        self.index += 1
        return value


def _combine_length_percentage(
    left: CSSMathValue,
    right: CSSMathValue,
    op: str,
) -> CSSMathValue | None:
    if left.kind not in {"length", "percentage", "length-percentage"}:
        return None
    if right.kind not in {"length", "percentage", "length-percentage"}:
        return None

    length_unit = _length_percentage_unit(left, right)
    if length_unit is None:
        return None

    left_length = _length_component(left, length_unit)
    right_length = _length_component(right, length_unit)
    left_percentage = _percentage_component(left)
    right_percentage = _percentage_component(right)
    sign = 1.0 if op == "+" else -1.0
    return CSSMathValue(
        left_length + sign * right_length,
        "length-percentage",
        length_unit,
        left_percentage + sign * right_percentage,
    )


def _length_percentage_unit(left: CSSMathValue, right: CSSMathValue) -> str | None:
    units = {
        value.unit
        for value in (left, right)
        if value.kind in {"length", "length-percentage"} and value.unit
    }
    if len(units) > 1:
        return None
    return next(iter(units), "px")


def _length_component(value: CSSMathValue, unit: str) -> float:
    if value.kind == "percentage":
        return 0.0
    if value.unit and value.unit != unit:
        raise CSSMathError("Cannot combine length-percentage units")
    return value.value


def _percentage_component(value: CSSMathValue) -> float:
    if value.kind == "percentage":
        return value.value
    if value.kind == "length-percentage":
        return value.percentage
    return 0.0


def _serialize_length_percentage(percentage: float, length: float, unit: str) -> str:
    if abs(length) <= 1e-12:
        return f"{percentage:g}%"
    if abs(percentage) <= 1e-12:
        return f"{length:g}{unit}"
    operator = "+" if length >= 0 else "-"
    return f"calc({percentage:g}% {operator} {abs(length):g}{unit})"


__all__ = [
    "CSSMathContext",
    "CSSMathError",
    "CSSMathValue",
    "evaluate_calc_function",
    "evaluate_calc_string",
    "simplify_calc_functions",
]
