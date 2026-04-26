from __future__ import annotations

import pytest

from svg2ooxml.core.resvg.parser.presentation import collect_presentation
from svg2ooxml.core.resvg.parser.tree import SvgNode


def _node(**attrs: str) -> SvgNode:
    return SvgNode(
        tag="text",
        attributes=attrs,
        styles={},
        children=[],
        text=None,
        tail=None,
    )


def test_collect_presentation_resolves_font_size_absolute_units_to_points() -> None:
    presentation = collect_presentation(_node(**{"font-size": "16px"}))

    assert presentation.font_size == pytest.approx(12.0)


def test_collect_presentation_resolves_font_size_percent_against_default_font() -> None:
    presentation = collect_presentation(_node(**{"font-size": "150%"}))

    assert presentation.font_size == pytest.approx(18.0)
    assert presentation.font_size_scale == pytest.approx(1.5)


def test_collect_presentation_parses_transform_compact_signed_numbers() -> None:
    presentation = collect_presentation(_node(transform="translate(10-20)"))

    assert presentation.transform is not None
    assert presentation.transform[0].values == pytest.approx((10.0, -20.0))


def test_collect_presentation_parses_percent_opacity() -> None:
    presentation = collect_presentation(_node(opacity="25%"))

    assert presentation.opacity == pytest.approx(0.25)
