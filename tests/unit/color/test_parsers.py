"""Tests for the shared color parser."""

from types import SimpleNamespace

import pytest

from svg2ooxml.color import TRANSPARENT, Color, parse_color
from svg2ooxml.color.adapters import color_object_alpha


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


def test_parse_rgb_percent_channels_quantizes_like_svg_engines() -> None:
    color = parse_color("rgb(99.9%, 50%, 0%)")

    assert color == Color(1.0, 128 / 255, 0.0, 1.0)


def test_parse_modern_space_separated_color_functions() -> None:
    rgb = parse_color("rgb(255 0 0 / 50%)")
    hsl = parse_color("hsl(240 100% 50% / 25%)")

    assert rgb == Color(1.0, 0.0, 0.0, 0.5)
    assert hsl is not None
    assert hsl.b == pytest.approx(1.0)
    assert hsl.a == pytest.approx(0.25)


def test_parse_color_functions_accept_calc_channels() -> None:
    rgb = parse_color("rgb(calc(255 - 127) calc(50% + 0%) 0 / calc(25% + 25%))")
    hsl = parse_color(
        "hsl(calc(0.25turn + 0.25turn) "
        "calc(50% + 50%) calc(25% + 25%) / calc(50% / 2))"
    )

    assert rgb is not None
    assert rgb.r == pytest.approx(128 / 255)
    assert rgb.g == pytest.approx(128 / 255)
    assert rgb.b == pytest.approx(0.0)
    assert rgb.a == pytest.approx(0.5)
    assert hsl is not None
    assert hsl.r == pytest.approx(0.0)
    assert hsl.g == pytest.approx(1.0)
    assert hsl.b == pytest.approx(1.0)
    assert hsl.a == pytest.approx(0.25)


def test_parse_oklab_and_oklch_accept_calc_components() -> None:
    oklab = parse_color(
        "oklab(calc(50% + 10%) calc(0.1 + 0.1) calc(0.05 - 0.01) / calc(25% + 25%))"
    )
    oklch = parse_color(
        "oklch(calc(50% + 10%) calc(0.2 + 0.1) calc(0.25turn + 90deg) / calc(0.4 + 0.1))"
    )

    assert oklab is not None
    assert oklab.a == pytest.approx(0.5)
    assert oklch is not None
    assert oklch.a == pytest.approx(0.5)


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


def test_parse_invalid_color_syntax_returns_none() -> None:
    assert parse_color("rgb(invalid)") is None
    assert parse_color("#12345") is None


def test_foreign_color_objects_reject_nonfinite_channels() -> None:
    assert parse_color(SimpleNamespace(r=float("nan"), g=0.0, b=0.0)) is None
    assert parse_color(SimpleNamespace(r=0.0, g=float("inf"), b=0.0)) is None


def test_foreign_color_alpha_rejects_nonfinite_values() -> None:
    assert color_object_alpha(
        SimpleNamespace(a=float("nan")),
        default=0.25,
    ) == pytest.approx(0.25)
