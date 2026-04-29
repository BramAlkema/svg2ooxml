"""Tests for mask baking helpers."""

from __future__ import annotations

import pytest

from svg2ooxml.core.masks.baker import try_bake_mask
from svg2ooxml.ir.paint import LinearGradientPaint, SolidPaint
from svg2ooxml.ir.scene import MaskDefinition, MaskRef


def test_try_bake_mask_resolves_calc_gradient_values() -> None:
    mask = MaskDefinition(
        mask_id="mask",
        content_xml=(
            """
            <linearGradient id="fade"
                x1="calc(25% + 25%)" y1="0%"
                x2="100%" y2="calc(25% + 25%)">
              <stop offset="calc(25% + 25%)" stop-color="#ffffff" stop-opacity="calc(25% + 25%)"/>
              <stop offset="100%" stop-color="#000000"/>
            </linearGradient>
            """,
        ),
    )

    fill, mask_ref = try_bake_mask(
        SolidPaint("112233"),
        MaskRef(mask_id="url(#mask)", definition=mask),
    )

    assert mask_ref is None
    assert isinstance(fill, LinearGradientPaint)
    assert fill.start == pytest.approx((0.5, 0.0))
    assert fill.end == pytest.approx((1.0, 0.5))
    assert fill.stops[0].offset == pytest.approx(0.5)
    assert fill.stops[0].opacity == pytest.approx(0.5)
