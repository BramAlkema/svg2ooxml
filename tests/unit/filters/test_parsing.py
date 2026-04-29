"""Tests for filter primitive parsing helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from lxml import etree

from svg2ooxml.filters.utils.parsing import (
    parse_displacement_map,
    parse_float_list,
    parse_length,
    parse_number,
    parse_turbulence,
)


def test_parse_length_resolves_context_free_calc() -> None:
    assert parse_length("calc(2px + 1px)") == pytest.approx(3.0)


def test_parse_length_resolves_contextual_calc_by_axis() -> None:
    context = SimpleNamespace(viewport={"width": 200.0, "height": 80.0})

    assert parse_length("calc(50% - 5px)", context=context, axis="x") == pytest.approx(95.0)
    assert parse_length("calc(50% - 5px)", context=context, axis="y") == pytest.approx(35.0)


def test_parse_length_sanitizes_nonfinite_viewport_context() -> None:
    context = SimpleNamespace(viewport={"width": "inf", "height": "bad"})

    assert parse_length("calc(50% + 1px)", context=context, axis="x") == pytest.approx(1.0)


def test_parse_length_returns_default_for_unresolved_calc() -> None:
    assert parse_length("calc(1em + 2px)", default=7.0) == pytest.approx(7.0)


def test_parse_filter_numbers_accept_calc() -> None:
    assert parse_number("calc(2 * 3)") == pytest.approx(6.0)
    assert parse_float_list("0 calc(1 + 2), calc(2 * 3)") == pytest.approx(
        [0.0, 3.0, 6.0]
    )


def test_parse_filter_structured_params_accept_calc() -> None:
    displacement = etree.fromstring(
        "<feDisplacementMap scale='calc(2 * 3)' xChannelSelector='R'/>"
    )
    turbulence = etree.fromstring(
        "<feTurbulence baseFrequency='calc(0.1 + 0.2) calc(0.4)' "
        "numOctaves='calc(1 + 1)' seed='calc(2 * 3)'/>"
    )

    displacement_params = parse_displacement_map(displacement)
    turbulence_params = parse_turbulence(turbulence)

    assert displacement_params.scale == pytest.approx(6.0)
    assert turbulence_params.base_frequency_x == pytest.approx(0.3)
    assert turbulence_params.base_frequency_y == pytest.approx(0.4)
    assert turbulence_params.num_octaves == 2
    assert turbulence_params.seed == pytest.approx(6.0)
