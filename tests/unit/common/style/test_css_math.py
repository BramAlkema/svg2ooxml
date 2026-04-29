"""Tests for typed CSS math evaluation."""

from __future__ import annotations

import pytest

from svg2ooxml.common.style.css_math import (
    CSSMathContext,
    CSSMathError,
    evaluate_calc_string,
    simplify_calc_functions,
)
from svg2ooxml.common.units import UnitConverter


def test_simplify_calc_functions_folds_compatible_context_free_units() -> None:
    assert simplify_calc_functions("calc(10px + 2px)") == "12px"
    assert simplify_calc_functions("calc(1in + 10px)") == "106px"
    assert simplify_calc_functions("calc(100% / 4)") == "25%"
    assert simplify_calc_functions("calc(2 * 1em)") == "2em"


def test_simplify_calc_functions_preserves_mixed_contextual_units() -> None:
    assert simplify_calc_functions("calc(100% - 10px)") == "calc(100% - 10px)"
    assert simplify_calc_functions("calc(25% + 5px)") == "calc(25% + 5px)"
    assert simplify_calc_functions("calc(1em + 2px)") == "calc(1em + 2px)"
    assert simplify_calc_functions("calc(10px + 2)") == "calc(10px + 2)"


def test_evaluate_calc_string_preserves_length_percentage_without_context() -> None:
    result = evaluate_calc_string("calc(100% - 10px)")

    assert result.kind == "length-percentage"
    assert result.percentage == pytest.approx(100.0)
    assert result.value == pytest.approx(-10.0)
    assert result.unit == "px"
    assert result.to_css() == "calc(100% - 10px)"


def test_evaluate_calc_string_scales_preserved_length_percentage() -> None:
    result = evaluate_calc_string("calc((100% - 10px) / 2)")

    assert result.kind == "length-percentage"
    assert result.percentage == pytest.approx(50.0)
    assert result.value == pytest.approx(-5.0)
    assert result.to_css() == "calc(50% - 5px)"


def test_evaluate_calc_string_resolves_percentages_with_explicit_axis() -> None:
    converter = UnitConverter()
    context = converter.create_context(width=200.0, height=80.0, font_size=10.0)

    x_context = CSSMathContext(
        conversion_context=context,
        unit_converter=converter,
        axis="x",
        percentage_basis="length",
    )
    y_context = CSSMathContext(
        conversion_context=context,
        unit_converter=converter,
        axis="y",
        percentage_basis="length",
    )

    assert evaluate_calc_string("calc(50% - 5px)", x_context).as_length_px(x_context) == pytest.approx(
        95.0
    )
    assert evaluate_calc_string("calc(50% - 5px)", y_context).as_length_px(y_context) == pytest.approx(
        35.0
    )


def test_evaluate_calc_string_handles_nested_parentheses_with_context() -> None:
    converter = UnitConverter()
    conversion = converter.create_context(width=200.0, height=80.0)
    context = CSSMathContext(
        conversion_context=conversion,
        unit_converter=converter,
        axis="x",
        percentage_basis="length",
    )

    result = evaluate_calc_string("calc((100% - 10px) / 2)", context)

    assert result.as_length_px(context) == pytest.approx(95.0)


def test_evaluate_calc_string_supports_angle_and_time_outputs() -> None:
    angle = evaluate_calc_string("calc(1turn - 90deg)")
    time = evaluate_calc_string("calc(1s + 250ms)")

    assert angle.kind == "angle"
    assert angle.as_degrees() == pytest.approx(270.0)
    assert angle.to_css() == "270deg"
    assert time.kind == "time"
    assert time.as_seconds() == pytest.approx(1.25)
    assert time.to_css() == "1.25s"


def test_evaluate_calc_string_rejects_invalid_type_arithmetic() -> None:
    with pytest.raises(CSSMathError):
        evaluate_calc_string("calc(10px / 2px)")

    with pytest.raises(CSSMathError):
        evaluate_calc_string("calc(1deg + 2px)")

    with pytest.raises(ZeroDivisionError):
        evaluate_calc_string("calc(10px / 0)")
