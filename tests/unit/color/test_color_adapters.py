"""Tests for color boundary adapters."""

from __future__ import annotations

import pytest

from svg2ooxml.color.adapters import (
    color_object_alpha,
    color_object_to_hex,
    css_color_to_hex,
    hex_to_rgba_tuple,
    rgba_tuple_to_hex,
)


class ForeignColor:
    def __init__(self, r: float, g: float, b: float, a: float = 1.0) -> None:
        self.r = r
        self.g = g
        self.b = b
        self.a = a


def test_color_object_to_hex_accepts_unit_and_byte_channels() -> None:
    assert color_object_to_hex(ForeignColor(1.0, 0.5, 0.0)) == "FF8000"
    assert color_object_to_hex(ForeignColor(255, 128, 0)) == "FF8000"


def test_color_object_alpha_accepts_unit_and_byte_alpha() -> None:
    assert color_object_alpha(ForeignColor(0, 0, 0, 0.25)) == pytest.approx(0.25)
    assert color_object_alpha(ForeignColor(0, 0, 0, 128)) == pytest.approx(128 / 255)


def test_css_color_to_hex_resolves_current_color() -> None:
    assert css_color_to_hex(
        "currentColor",
        current_color=(0.2, 0.4, 0.6, 1.0),
        prefix="#",
    ) == "#336699"


def test_rgba_tuple_helpers_roundtrip_hex() -> None:
    rgba = hex_to_rgba_tuple("#336699")

    assert rgba == pytest.approx((0.2, 0.4, 0.6, 1.0))
    assert rgba is not None
    assert rgba_tuple_to_hex(rgba, prefix="#") == "#336699"
