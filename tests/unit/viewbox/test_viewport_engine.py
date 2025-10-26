"""Tests for the viewport engine."""

import pytest

from svg2ooxml.viewbox.core import (
    PreserveAspectRatio,
    ViewportEngine,
    compute_viewbox,
    parse_preserve_aspect_ratio,
)


def test_compute_viewbox_preserves_aspect_ratio() -> None:
    engine = ViewportEngine()
    result = engine.compute((0, 0, 100, 50), (200, 200), "xMidYMid meet")

    assert result.scale_x == pytest.approx(2.0)
    assert result.scale_y == pytest.approx(2.0)
    assert result.translate_x == pytest.approx(0.0)
    assert result.translate_y == pytest.approx(50.0)


def test_compute_viewbox_none_allows_non_uniform_scale() -> None:
    result = compute_viewbox((0, 0, 100, 50), (300, 200), "none")

    assert result.scale_x == pytest.approx(3.0)
    assert result.scale_y == pytest.approx(4.0)
    assert result.translate_x == 0.0
    assert result.translate_y == 0.0


def test_compute_viewbox_slice_mode() -> None:
    result = compute_viewbox((0, 0, 100, 50), (200, 200), "xMidYMid slice")

    assert result.scale_x == pytest.approx(4.0)
    assert result.scale_y == pytest.approx(4.0)
    # With slice the translation offsets should be negative to crop.
    assert result.translate_x == pytest.approx(-100.0)
    assert result.translate_y == pytest.approx(0.0)


def test_parse_preserve_aspect_ratio_defaults() -> None:
    parsed = parse_preserve_aspect_ratio(None)

    assert parsed == PreserveAspectRatio()


def test_parse_preserve_aspect_ratio_defer_flag() -> None:
    parsed = parse_preserve_aspect_ratio("defer xMaxYMin slice")

    assert parsed.defer is True
    assert parsed.align == "xmaxymin"
    assert parsed.meet_or_slice == "slice"
