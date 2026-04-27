"""Tests for contextual SVG length resolution."""

from __future__ import annotations

import pytest

from svg2ooxml.common.style.css_values import resolve_calc
from svg2ooxml.common.units import UnitConverter
from svg2ooxml.common.units.lengths import (
    parse_number_or_percent,
    resolve_length_list_px,
    resolve_length_px,
    resolve_user_length_px,
    split_length_list,
)


def test_resolve_length_px_handles_mixed_unit_calc() -> None:
    converter = UnitConverter()
    context = converter.create_context(width=200.0, height=80.0, font_size=16.0)

    assert resolve_length_px(
        "calc(100% - 10px)",
        context,
        axis="x",
        unit_converter=converter,
    ) == pytest.approx(190.0)
    assert resolve_length_px(
        "calc(50% + 1em)",
        context,
        axis="y",
        unit_converter=converter,
    ) == pytest.approx(56.0)


def test_resolve_length_px_supports_calc_multiplication_and_division() -> None:
    context = UnitConverter().create_context(width=100.0, height=100.0, font_size=12.0)

    assert resolve_length_px("calc(2 * 1em)", context, axis="x") == pytest.approx(24.0)
    assert resolve_length_px("calc(100% / 4)", context, axis="x") == pytest.approx(25.0)


def test_resolve_length_list_px_preserves_calc_tokens() -> None:
    context = UnitConverter().create_context(width=100.0, height=50.0, font_size=10.0)

    assert split_length_list("0 calc(50% - 2px), 1em") == [
        "0",
        "calc(50% - 2px)",
        "1em",
    ]
    assert resolve_length_list_px(
        "0 calc(50% - 2px), 1em",
        context,
        axis="x",
    ) == pytest.approx([0.0, 48.0, 10.0])


def test_user_length_and_fraction_helpers_share_semantics() -> None:
    assert parse_number_or_percent("25%", 0.0) == pytest.approx(0.25)
    assert resolve_user_length_px("25%", 0.0, 80.0) == pytest.approx(20.0)
    assert resolve_user_length_px("calc(25% + 5px)", 0.0, 80.0) == pytest.approx(25.0)


def test_context_free_calc_preserves_mixed_units_for_later_resolution() -> None:
    assert resolve_calc("calc(100% - 10px)") == "calc(100% - 10px)"
    assert resolve_calc("calc(10px + 2px)") == "12px"
