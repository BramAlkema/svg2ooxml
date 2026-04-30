"""Filter planner safety and policy tests."""

from __future__ import annotations

import math

import pytest
from lxml import etree

from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.planner import FilterPlanner
from svg2ooxml.filters.resvg_bridge import resolve_filter_element
from svg2ooxml.filters.strategies.resvg_promotion import is_neutral_promotion


def _descriptor(markup: str):
    return resolve_filter_element(
        etree.fromstring(f"<svg xmlns='http://www.w3.org/2000/svg'>{markup}</svg>")[0]
    )


def test_resvg_bounds_sanitizes_non_finite_object_bbox_region_values() -> None:
    planner = FilterPlanner()
    descriptor = _descriptor(
        "<filter id='unsafe' x='nan' y='inf' width='inf' height='nan'>"
        "  <feGaussianBlur stdDeviation='2'/>"
        "</filter>"
    )

    bounds = planner.resvg_bounds(
        {"ir_bbox": {"x": 0.0, "y": 0.0, "width": 100.0, "height": 50.0}},
        descriptor,
    )

    assert bounds == pytest.approx((-10.0, -5.0, 110.0, 55.0))


def test_resvg_bounds_sanitizes_non_finite_user_space_region_values() -> None:
    planner = FilterPlanner()
    descriptor = _descriptor(
        "<filter id='unsafe' filterUnits='userSpaceOnUse'"
        "        x='nan' y='inf' width='-inf' height='50%'>"
        "  <feGaussianBlur stdDeviation='2'/>"
        "</filter>"
    )

    bounds = planner.resvg_bounds(
        {
            "ir_bbox": {"x": 20.0, "y": 10.0, "width": 100.0, "height": 50.0},
            "viewport_width": math.inf,
            "viewport_height": 200.0,
        },
        descriptor,
    )

    assert bounds == pytest.approx((10.0, 5.0, 130.0, 105.0))


def test_resolve_filter_element_resolves_number_calc_dimensions() -> None:
    descriptor = _descriptor(
        "<filter id='calc-region' x='calc(1 + 2)' width='calc(10 * 2)'>"
        "  <feGaussianBlur stdDeviation='2'/>"
        "</filter>"
    )

    assert descriptor.region["x"] == pytest.approx(3.0)
    assert descriptor.region["width"] == pytest.approx(20.0)


def test_resolve_filter_element_skips_descriptive_filter_children() -> None:
    descriptor = _descriptor(
        "<filter id='background'>"
        "  <desc>test metadata</desc>"
        "  <feOffset in='BackgroundImage' result='offset' dx='0' dy='125'/>"
        "  <title>not a primitive</title>"
        "  <metadata><ignored/></metadata>"
        "  <feGaussianBlur in='offset' stdDeviation='8'/>"
        "</filter>"
    )

    assert [primitive.tag for primitive in descriptor.primitives] == [
        "feOffset",
        "feGaussianBlur",
    ]
    plan = FilterPlanner().build_resvg_plan(
        descriptor,
        options={"available_filter_inputs": ["BackgroundImage"]},
    )

    assert plan is not None
    assert [primitive.tag for primitive in plan.primitives] == [
        "feOffset",
        "feGaussianBlur",
    ]


def test_resvg_viewport_rejects_non_finite_or_huge_bounds() -> None:
    planner = FilterPlanner()

    with pytest.raises(ValueError):
        planner.resvg_viewport((0.0, 0.0, math.inf, 10.0))

    with pytest.raises(ValueError):
        planner.resvg_viewport((0.0, 0.0, 4097.0, 10.0))


def test_descriptor_payload_filters_non_finite_bbox_and_region_values() -> None:
    planner = FilterPlanner()
    context = FilterContext(
        filter_element=etree.Element("filter"),
        options={
            "ir_bbox": {
                "x": math.inf,
                "y": "nan",
                "width": "64",
                "height": 48,
            }
        },
    )

    _, bounds = planner.descriptor_payload(context, descriptor=None)

    assert bounds == {"width": 64.0, "height": 48.0}
    assert planner._numeric_region(
        {"x": "nan", "y": "2", "width": math.inf, "height": 4}
    ) == {"y": 2.0, "height": 4.0}


def test_policy_overrides_reject_non_finite_limits() -> None:
    planner = FilterPlanner()
    context = FilterContext(
        filter_element=etree.Element("filter"),
        options={
            "policy": {
                "primitives": {
                    "feGaussianBlur": {
                        "allow_resvg": "false",
                        "max_pixels": math.inf,
                        "max_offset_distance": "nan",
                    }
                }
            }
        },
    )

    assert planner.policy_primitive_overrides(context) == {
        "fegaussianblur": {"allow_resvg": False}
    }


def test_promotion_policy_ignores_non_finite_limits() -> None:
    result = FilterResult(
        success=True,
        fallback="emf",
        metadata={"dx": 100.0, "dy": 0.0},
    )

    assert FilterPlanner.promotion_policy_allows(
        "feoffset",
        result,
        {"max_offset_distance": math.nan},
    )


def test_neutral_promotion_falls_back_to_gaussian_blur_element() -> None:
    non_neutral = etree.fromstring("<feGaussianBlur stdDeviation='calc(1px + 1px)'/>")
    neutral = etree.fromstring("<feGaussianBlur stdDeviation='calc(0px + 0px), 0'/>")
    result = FilterResult(success=True, metadata={})

    assert not is_neutral_promotion("fegaussianblur", non_neutral, result)
    assert is_neutral_promotion("fegaussianblur", neutral, result)


def test_descriptor_neutral_detection_accepts_calc_offsets() -> None:
    planner = FilterPlanner()
    descriptor = _descriptor(
        "<filter id='neutral'>"
        "  <feOffset dx='calc(2 - 2)' dy='calc(3 - 3)'/>"
        "</filter>"
    )

    assert planner.descriptor_is_neutral(descriptor)
