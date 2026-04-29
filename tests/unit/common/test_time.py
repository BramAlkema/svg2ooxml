"""Tests for shared time parsing helpers."""

from __future__ import annotations

import pytest

from svg2ooxml.common.time import parse_time_value


def test_parse_time_value_preserves_existing_units() -> None:
    assert parse_time_value("250ms") == pytest.approx(0.25)
    assert parse_time_value("2s") == pytest.approx(2.0)
    assert parse_time_value("1.5min") == pytest.approx(90.0)
    assert parse_time_value("0.5h") == pytest.approx(1800.0)


def test_parse_time_value_supports_calc_time_units() -> None:
    assert parse_time_value("calc(1s + 250ms)") == pytest.approx(1.25)
    assert parse_time_value("calc(1min + 30s)") == pytest.approx(90.0)
    assert parse_time_value("calc(2s / 4)") == pytest.approx(0.5)


def test_parse_time_value_invalid_calc_falls_back_to_zero() -> None:
    assert parse_time_value("calc(1s + 2px)") == 0.0
    assert parse_time_value("calc(1s / 0)") == 0.0
