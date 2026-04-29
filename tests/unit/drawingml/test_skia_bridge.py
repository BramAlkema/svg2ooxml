from __future__ import annotations

from svg2ooxml.drawingml.skia_bridge import _coerce_bounds


def test_coerce_bounds_rejects_nonfinite_offsets_and_clamps_size() -> None:
    assert _coerce_bounds(
        {"x": "nan", "y": 0, "width": 10, "height": 10},
        default_width=20,
        default_height=30,
    ) is None
    assert _coerce_bounds(
        {"x": 1, "y": 2, "width": -1, "height": "bad"},
        default_width=20,
        default_height=30,
    ) == (1.0, 2.0, 20.0, 30.0)
