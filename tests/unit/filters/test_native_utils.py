"""Tests for shared native filter helper parsing."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from svg2ooxml.filters.renderer_compat import FilterRendererCompatibilityMixin
from svg2ooxml.filters.strategies.native_utils import (
    aggregate_blip_color_transforms,
    coerce_non_negative_float,
    component_transfer_alpha_scale,
    parse_float_attr,
)


class _IdentityTransfer:
    @staticmethod
    def _is_identity_function(_function: object) -> bool:
        return True


def test_native_float_helpers_accept_calc_numbers() -> None:
    assert parse_float_attr("calc(1 + 2)") == pytest.approx(3.0)
    assert coerce_non_negative_float("calc(8 / 2)") == pytest.approx(4.0)
    assert coerce_non_negative_float("calc(-1)") is None


def test_filter_renderer_compat_float_wrappers_accept_calc() -> None:
    assert FilterRendererCompatibilityMixin._parse_float_attr("calc(1 + 2)") == 3.0
    assert FilterRendererCompatibilityMixin._coerce_non_negative_float("calc(8 / 2)") == 4.0
    assert FilterRendererCompatibilityMixin._coerce_non_negative_float("calc(-1)") is None


def test_component_transfer_alpha_scale_accepts_calc_params() -> None:
    function = SimpleNamespace(
        channel="a",
        func_type="linear",
        params={"slope": "calc(0.25 + 0.25)", "intercept": "calc(0)"},
    )

    scale = component_transfer_alpha_scale(_IdentityTransfer(), [function])

    assert scale == pytest.approx(0.5)


def test_aggregate_blip_color_transforms_accepts_calc_values() -> None:
    result = aggregate_blip_color_transforms(
        [
            {"tag": "alphaModFix", "amt": "calc(50000 + 25000)"},
            {"tag": "satMod", "val": "calc(25000 * 2)"},
            {"tag": "hueOff", "val": "calc(5400000 + 2700000)"},
        ]
    )

    assert result == [
        {"tag": "alphaModFix", "amt": 75000},
        {"tag": "satMod", "val": 50000},
        {"tag": "hueOff", "val": 8100000},
    ]
