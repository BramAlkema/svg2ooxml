"""Tests for the shared color parser."""

import pytest

from svg2ooxml.color import TRANSPARENT, Color, parse_color


def test_parse_named_color() -> None:
    color = parse_color("rebeccapurple")

    assert color is not None
    assert color.to_hex() == "#663399"


def test_parse_hex_with_alpha() -> None:
    color = parse_color("#33669980")

    assert color is not None
    assert color.a == pytest.approx(128 / 255.0)


def test_parse_rgb_and_hsl() -> None:
    rgb = parse_color("rgb(255, 0, 0)")
    hsl = parse_color("hsl(120, 100%, 25%)")

    assert rgb == Color(1.0, 0.0, 0.0, 1.0)
    assert hsl is not None
    assert hsl.g > 0.0 and hsl.r < 0.2


def test_parse_current_color() -> None:
    base = Color(0.1, 0.2, 0.3, 0.4)

    assert parse_color("currentColor", current_color=base) == base


def test_parse_palette_entries() -> None:
    palette = {
        "brand": "#336699",
        "accent": Color(0.2, 0.4, 0.6, 1.0),
    }

    assert parse_color("brand", palette=palette).to_hex() == "#336699"
    assert parse_color("accent", palette=palette) == Color(0.2, 0.4, 0.6, 1.0)


def test_parse_transparent_keyword() -> None:
    assert parse_color("transparent") == TRANSPARENT


def test_parse_unknown_returns_none() -> None:
    assert parse_color("not-a-color") is None
