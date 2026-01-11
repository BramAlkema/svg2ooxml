"""Smoke tests for the advanced colour engine port."""

from __future__ import annotations

import pytest

pytest.importorskip("numpy")
pytest.importorskip("colorspacious")

from svg2ooxml.color.advanced.accessibility import ColorAccessibility, ContrastLevel
from svg2ooxml.color.advanced.engine import AdvancedColor
from svg2ooxml.color.advanced.harmony import ColorHarmony
from svg2ooxml.color.bridge import (
    ADVANCED_COLOR_ENGINE_AVAILABLE,
    ensure_advanced_color_engine,
    from_advanced_color,
    to_advanced_color,
)
from svg2ooxml.color.models import Color


if not ADVANCED_COLOR_ENGINE_AVAILABLE:
    pytest.skip("Advanced colour engine dependencies are not installed.", allow_module_level=True)


ensure_advanced_color_engine()


def test_advanced_color_hex_roundtrip() -> None:
    colour = AdvancedColor("#336699")
    assert colour.rgb() == (51, 102, 153)
    assert colour.hex(include_hash=True) == "#336699"
    assert colour.rgba()[3] == pytest.approx(1.0)


def test_advanced_color_lighten_and_darken() -> None:
    base = AdvancedColor("#663399")

    lighter = base.lighten(0.2)
    darker = base.darken(0.2)

    assert lighter.rgb() != base.rgb()
    assert darker.rgb() != base.rgb()


def test_bridge_roundtrip_between_models() -> None:
    simple = Color(0.25, 0.5, 0.75, 0.5)

    advanced = to_advanced_color(simple)
    assert advanced.rgb() == (64, 128, 191)
    assert advanced.rgba()[3] == pytest.approx(0.5, rel=1e-3)

    roundtrip = from_advanced_color(advanced)
    tol = 1.0 / 255.0
    assert roundtrip.a == pytest.approx(simple.a, abs=tol)
    assert roundtrip.r == pytest.approx(simple.r, abs=tol)
    assert roundtrip.g == pytest.approx(simple.g, abs=tol)
    assert roundtrip.b == pytest.approx(simple.b, abs=tol)


def test_bridge_accepts_float_sequences() -> None:
    advanced = to_advanced_color((0.1, 0.2, 0.3, 0.4))
    assert advanced.rgb() == (26, 51, 76)
    assert advanced.rgba()[3] == pytest.approx(0.4, rel=1e-3)


def test_colour_harmony_generation() -> None:
    base = AdvancedColor("#6699cc")
    harmony = ColorHarmony(base)
    palette = harmony.analogous(count=3)

    assert len(palette) == 3
    assert all(isinstance(item, AdvancedColor) for item in palette)


def test_accessibility_contrast_ratio() -> None:
    text = AdvancedColor("#333333")
    background = AdvancedColor("#ffffff")
    toolkit = ColorAccessibility()
    ratio = toolkit.contrast_ratio(text, background)

    assert ratio >= ContrastLevel.AA_NORMAL.value
