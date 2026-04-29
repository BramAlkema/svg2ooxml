"""Tests for shared point-list parsing."""

from __future__ import annotations

from svg2ooxml.common.geometry.points import parse_point_pairs, parse_point_values


def test_parse_point_pairs_handles_compact_signed_values() -> None:
    assert parse_point_pairs("0,0 10-5 20,0") == [
        (0.0, 0.0),
        (10.0, -5.0),
        (20.0, 0.0),
    ]


def test_parse_point_pairs_drops_trailing_odd_coordinate() -> None:
    assert parse_point_pairs("0,0 10,5 20") == [(0.0, 0.0), (10.0, 5.0)]


def test_parse_point_pairs_accepts_number_calc_values() -> None:
    assert parse_point_pairs("calc(1 + 2),4 5,calc(3 * 2)") == [
        (3.0, 4.0),
        (5.0, 6.0),
    ]


def test_parse_point_values_returns_flattened_even_values() -> None:
    assert parse_point_values("0,0 10-5 20,0") == (0.0, 0.0, 10.0, -5.0, 20.0, 0.0)
