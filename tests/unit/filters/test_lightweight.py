"""Lightweight filter planner tests."""

from __future__ import annotations

import math

from lxml import etree

from svg2ooxml.filters.base import FilterContext
from svg2ooxml.filters.lightweight import LightweightFilterPlanner
from svg2ooxml.filters.planner import FilterPlanner
from svg2ooxml.filters.resvg_bridge import resolve_filter_element


def _descriptor(markup: str):
    return resolve_filter_element(
        etree.fromstring(f"<svg xmlns='http://www.w3.org/2000/svg'>{markup}</svg>")[0]
    )


def test_lightweight_descriptor_payload_filters_non_finite_bbox_values() -> None:
    planner = LightweightFilterPlanner()
    context = FilterContext(
        filter_element=etree.Element("filter"),
        options={
            "ir_bbox": {
                "x": "inf",
                "y": math.nan,
                "width": "120",
                "height": 60,
            }
        },
    )

    assert planner.descriptor_payload(context, descriptor=None) == (
        None,
        {"width": 120.0, "height": 60.0},
    )


def test_lightweight_descriptor_payload_filters_non_finite_region_values() -> None:
    planner = LightweightFilterPlanner()
    descriptor = _descriptor(
        "<filter id='blur' x='nan' y='2' width='inf' height='4'>"
        "  <feGaussianBlur stdDeviation='2'/>"
        "</filter>"
    )
    context = FilterContext(filter_element=etree.Element("filter"), options={})

    payload, bounds = planner.descriptor_payload(context, descriptor)

    assert payload is not None
    assert bounds == {"y": 2.0, "height": 4.0}


def test_lightweight_policy_overrides_reject_non_finite_limits() -> None:
    planner = LightweightFilterPlanner()
    context = FilterContext(
        filter_element=etree.Element("filter"),
        options={
            "policy": {
                "primitives": {
                    "feOffset": {
                        "allow_resvg": "false",
                        "max_pixels": math.inf,
                        "max_offset_distance": "nan",
                    }
                }
            }
        },
    )

    assert planner.policy_primitive_overrides(context) == {
        "feoffset": {"allow_resvg": False}
    }


def test_lightweight_descriptor_strategy_matches_full_planner() -> None:
    descriptor = {"primitive_tags": ["feImage"]}
    lightweight = LightweightFilterPlanner()
    full = FilterPlanner()

    assert lightweight.infer_descriptor_strategy(
        descriptor,
        strategy_hint="auto",
    ) == full.infer_descriptor_strategy(descriptor, strategy_hint="auto")
