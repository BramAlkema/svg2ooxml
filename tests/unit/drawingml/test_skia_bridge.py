from __future__ import annotations

import pytest

from svg2ooxml.drawingml.skia_bridge import (
    _coerce_bounds,
    render_surface_from_descriptor,
)


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


def test_render_surface_from_descriptor_respects_explicit_bounds() -> None:
    pytest.importorskip("skia")

    descriptor = {
        "shape_type": "Path",
        "geometry": [
            {"type": "line", "start": (10.0, 10.0), "end": (30.0, 10.0)},
            {"type": "line", "start": (30.0, 10.0), "end": (30.0, 30.0)},
            {"type": "line", "start": (30.0, 30.0), "end": (10.0, 30.0)},
            {"type": "line", "start": (10.0, 30.0), "end": (10.0, 10.0)},
        ],
        "closed": True,
        "fill": {"type": "solid", "rgb": "00FF00", "opacity": 1.0},
        "stroke": None,
        "opacity": 1.0,
        "bbox": {"x": 10.0, "y": 10.0, "width": 20.0, "height": 20.0},
    }

    surface = render_surface_from_descriptor(
        descriptor=descriptor,
        bounds={"x": 0.0, "y": 0.0, "width": 40.0, "height": 40.0},
        width_px=40,
        height_px=40,
    )

    assert surface is not None
    assert float(surface.data[20, 20, 3]) > 0.8
    assert float(surface.data[5, 5, 3]) == 0.0
    assert float(surface.data[35, 35, 3]) == 0.0
