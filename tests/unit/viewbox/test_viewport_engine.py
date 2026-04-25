"""Tests for the viewport engine."""

import pytest

from svg2ooxml.core.traversal.viewbox import (
    PreserveAspectRatio,
    ViewportEngine,
    compute_viewbox,
    parse_preserve_aspect_ratio,
    parse_viewbox_attribute,
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


def test_compute_viewbox_rejects_negative_viewbox_dimensions() -> None:
    with pytest.raises(ValueError, match="viewBox width/height must be positive"):
        compute_viewbox((0, 0, -100, 50), (200, 200), "none")


def test_parse_preserve_aspect_ratio_defaults() -> None:
    parsed = parse_preserve_aspect_ratio(None)

    assert parsed == PreserveAspectRatio()


def test_parse_preserve_aspect_ratio_defer_flag() -> None:
    parsed = parse_preserve_aspect_ratio("defer xMaxYMin slice")

    assert parsed.defer is True
    assert parsed.align == "xmaxymin"
    assert parsed.meet_or_slice == "slice"


def test_parse_viewbox_accepts_compact_signed_numbers() -> None:
    parsed = parse_viewbox_attribute("-10-20 100 50")

    assert parsed is not None
    assert parsed.min_x == pytest.approx(-10.0)
    assert parsed.min_y == pytest.approx(-20.0)
    assert parsed.width == pytest.approx(100.0)
    assert parsed.height == pytest.approx(50.0)


def test_parse_viewbox_rejects_non_numeric_garbage() -> None:
    with pytest.raises(ValueError, match="viewBox contains non-numeric values"):
        parse_viewbox_attribute("garbage 0 0 100 50")
