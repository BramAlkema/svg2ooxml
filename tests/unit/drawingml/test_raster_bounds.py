"""Raster filter bounds helper tests."""

from __future__ import annotations

import math

import pytest

from svg2ooxml.drawingml.raster_bounds import (
    descriptor_payload,
    parse_object_bbox_region_value,
    parse_region_value,
    resolved_filter_bounds,
)


class _Context:
    def __init__(self, options: dict[str, object]) -> None:
        self.options = options


def test_region_value_parsers_reject_non_finite_values() -> None:
    assert parse_region_value("nan", reference=100.0) is None
    assert parse_region_value("inf", reference=100.0) is None
    assert parse_region_value("50%", reference=math.inf) is None
    assert parse_object_bbox_region_value("inf", reference=100.0) is None
    assert parse_object_bbox_region_value("25%", reference=math.nan) is None


def test_resolved_filter_bounds_ignores_non_finite_bounds_and_region() -> None:
    bounds = {
        "x": math.inf,
        "y": math.nan,
        "width": math.inf,
        "height": "bad",
    }
    descriptor = {
        "filter_units": "userSpaceOnUse",
        "filter_region": {
            "x": "nan",
            "y": "inf",
            "width": "-inf",
            "height": "50%",
        },
    }

    result = resolved_filter_bounds(
        descriptor=descriptor,
        bounds=bounds,
        default_width=100.0,
        default_height=80.0,
    )

    assert result == pytest.approx({"x": 0.0, "y": 0.0, "width": 100.0, "height": 40.0})


def test_object_bounding_box_bounds_ignore_non_finite_region_parts() -> None:
    result = resolved_filter_bounds(
        descriptor={
            "filter_units": "objectBoundingBox",
            "filter_region": {
                "x": "inf",
                "y": "nan%",
                "width": "2",
                "height": "nan",
            },
        },
        bounds={"x": 10.0, "y": 20.0, "width": 100.0, "height": 50.0},
        default_width=100.0,
        default_height=50.0,
    )

    assert result == pytest.approx(
        {"x": 10.0, "y": 20.0, "width": 200.0, "height": 50.0}
    )


def test_descriptor_payload_filters_non_finite_bbox_values() -> None:
    _, bounds = descriptor_payload(
        _Context(
            {
                "ir_bbox": {
                    "x": "inf",
                    "y": "nan",
                    "width": "12",
                    "height": 8,
                }
            }
        )
    )

    assert bounds == {"width": 12.0, "height": 8.0}
