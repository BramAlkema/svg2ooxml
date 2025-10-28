"""Tests for color parsing helpers."""

from svg2ooxml.core.parser import parse_color, register_palette


def test_parse_color_handles_hex() -> None:
    color = parse_color("#336699")

    assert color == (0x33 / 255.0, 0x66 / 255.0, 0x99 / 255.0, 1.0)


def test_parse_color_handles_short_hex() -> None:
    color = parse_color("#fff")

    assert color == (1.0, 1.0, 1.0, 1.0)


def test_parse_color_handles_rgb_and_rgba() -> None:
    rgb = parse_color("rgb(255, 0, 0)")
    rgba = parse_color("rgba(0, 0, 255, 0.5)")

    assert rgb == (1.0, 0.0, 0.0, 1.0)
    assert rgba == (0.0, 0.0, 1.0, 0.5)


def test_parse_color_handles_currentcolor() -> None:
    fallback = (0.2, 0.3, 0.4, 1.0)
    color = parse_color("currentColor", current_color=fallback)

    assert color == fallback


def test_parse_color_returns_none_for_unknown() -> None:
    assert parse_color("not-a-color") is None


def test_parse_color_uses_custom_palette() -> None:
    register_palette({"brand": (0.1, 0.2, 0.3, 1.0)})

    assert parse_color("brand") == (0.1, 0.2, 0.3, 1.0)


def test_parse_color_accepts_inline_palette() -> None:
    palette = {"accent": (0.5, 0.5, 0.0, 1.0)}

    assert parse_color("accent", palette=palette) == (0.5, 0.5, 0.0, 1.0)
