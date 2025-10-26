from __future__ import annotations

import math

from svg2ooxml.color import (
    Color,
    oklab_to_oklch,
    oklab_to_rgb,
    oklch_to_oklab,
    oklch_to_rgb,
    rgb_to_oklab,
    rgb_to_oklch,
)


def _approx_tuple(actual: tuple[float, ...], expected: tuple[float, ...], *, tol: float = 1e-6) -> None:
    assert len(actual) == len(expected)
    for act, exp in zip(actual, expected):
        assert math.isclose(act, exp, rel_tol=tol, abs_tol=tol)


def test_rgb_oklab_round_trip() -> None:
    original = (0.2, 0.4, 0.9)
    lab = rgb_to_oklab(*original)
    converted = oklab_to_rgb(*lab)
    _approx_tuple(converted, original, tol=1e-4)


def test_rgb_oklch_round_trip() -> None:
    original = (0.8, 0.3, 0.6)
    l, c, h = rgb_to_oklch(*original)
    converted = oklch_to_rgb(l, c, h)
    _approx_tuple(converted, original, tol=1e-4)


def test_oklab_oklch_conversion() -> None:
    lab = (0.5, 0.1, -0.2)
    lch = oklab_to_oklch(*lab)
    assert math.isclose(lch[0], lab[0], rel_tol=1e-6)
    recovered = oklch_to_oklab(*lch)
    _approx_tuple(recovered, lab, tol=1e-6)


def test_color_model_helpers() -> None:
    color = Color(0.3, 0.6, 0.9)
    lab = color.to_oklab()
    regenerated = Color.from_oklab(*lab)
    _approx_tuple((regenerated.r, regenerated.g, regenerated.b), (0.3, 0.6, 0.9), tol=1e-4)

    lch = color.to_oklch()
    regenerated_lch = Color.from_oklch(*lch)
    _approx_tuple((regenerated_lch.r, regenerated_lch.g, regenerated_lch.b), (0.3, 0.6, 0.9), tol=1e-4)
