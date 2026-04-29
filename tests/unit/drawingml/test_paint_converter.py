from __future__ import annotations

from svg2ooxml.drawingml.paint_converter import (
    _coerce_positive,
    _float_or,
    _is_number,
    _is_point_pair,
)


def test_float_or_uses_default_for_invalid_and_nonfinite_values() -> None:
    assert _float_or("2.5", 1.0) == 2.5
    assert _float_or("bad", 1.0) == 1.0
    assert _float_or("inf", 1.0) == 1.0


def test_point_pair_requires_finite_numeric_values() -> None:
    assert _is_point_pair((1, "2.5")) is True
    assert _is_point_pair((1, "inf")) is False
    assert _is_point_pair((1, "bad")) is False


def test_coerce_positive_uses_fallback_for_nonpositive_values() -> None:
    assert _coerce_positive("2", fallback=1.0) == 2.0
    assert _coerce_positive("-1", fallback=1.0) == 1.0
    assert _coerce_positive("bad") == 0.0


def test_is_number_rejects_nonfinite_values() -> None:
    assert _is_number("3") is True
    assert _is_number("nan") is False
