from __future__ import annotations

from svg2ooxml.drawingml.filter_fallback import resolve_filter_fallback_bounds
from svg2ooxml.ir.geometry import Rect


def test_filter_fallback_bounds_resolve_calc_lengths() -> None:
    bounds = resolve_filter_fallback_bounds(
        Rect(10.0, 20.0, 30.0, 40.0),
        {
            "bounds": {
                "x": "calc(1px + 4px)",
                "y": "calc(10px + 5px)",
                "width": "calc(25px * 2)",
                "height": "calc(20px * 3)",
            }
        },
    )

    assert bounds == Rect(5.0, 15.0, 50.0, 60.0)


def test_filter_fallback_bounds_keep_default_on_invalid_override() -> None:
    default = Rect(10.0, 20.0, 30.0, 40.0)

    bounds = resolve_filter_fallback_bounds(default, {"bounds": {"x": "bad"}})

    assert bounds == default
