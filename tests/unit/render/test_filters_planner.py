"""Tests for render filter planning helpers."""

from __future__ import annotations

import pytest

from svg2ooxml.render.filters_planner import (
    _parse_float_list,
    _parse_number,
    _parse_std_deviation,
)


def test_parse_std_deviation_accepts_calc_lengths() -> None:
    assert _parse_std_deviation("calc(1px + 2px), calc(0.25in - 6pt)") == pytest.approx(
        (3.0, 16.0)
    )


def test_parse_filter_numbers_accept_calc() -> None:
    assert _parse_number("calc(50% / 2)") == pytest.approx(0.25)
    assert _parse_number("calc(2 * 3)") == pytest.approx(6.0)
    assert _parse_float_list("1, calc(2 * 3) bad") == pytest.approx([1.0, 6.0])
