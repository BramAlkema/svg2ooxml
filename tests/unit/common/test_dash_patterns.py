from __future__ import annotations

import math

from svg2ooxml.common.dash_patterns import normalize_dash_array


def test_normalize_dash_array_keeps_finite_positive_lengths() -> None:
    assert normalize_dash_array([4, "2.5", 0, math.nan, math.inf, "bad"]) == [
        4.0,
        2.5,
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
