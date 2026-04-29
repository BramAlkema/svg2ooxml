from __future__ import annotations

import math

import pytest

from svg2ooxml.common.dash_patterns import normalize_dash_array, parse_dash_array


def test_normalize_dash_array_keeps_finite_positive_lengths() -> None:
    assert normalize_dash_array([4, "2.5", "calc(1 + 2)", "6", 0, math.nan, math.inf, "bad"]) == [
        4.0,
        2.5,
        3.0,
        6.0,
    ]


def test_normalize_dash_array_abs_values_and_doubles_odd_arrays() -> None:
    assert normalize_dash_array([-4.0, 2.0, 1.0]) == [
        4.0,
        2.0,
        1.0,
        4.0,
        2.0,
        1.0,
    ]


def test_parse_dash_array_resolves_units_and_calc() -> None:
    assert parse_dash_array("0.25in calc(6pt + 2pt)") == pytest.approx([24.0, 32.0 / 3.0])


def test_parse_dash_array_treats_percentages_as_svg_percent_units() -> None:
    assert parse_dash_array("50% calc(25% + 25%)") == pytest.approx([50.0, 50.0])


def test_parse_dash_array_rejects_invalid_values() -> None:
    assert parse_dash_array("4 bad") is None
    assert parse_dash_array("none") is None
