from __future__ import annotations

from lxml import etree

from svg2ooxml.filters.base import FilterContext
from svg2ooxml.filters.primitives.color_matrix import ColorMatrixFilter
from svg2ooxml.filters.primitives.component_transfer import ComponentTransferFilter


def _context(*, enable_native_color_transforms: bool) -> FilterContext:
    return FilterContext(
        filter_element=etree.Element("filter"),
        options={"policy": {"enable_native_color_transforms": enable_native_color_transforms}},
    )


def test_color_matrix_saturate_records_blip_transform_candidates() -> None:
    primitive = etree.fromstring('<feColorMatrix type="saturate" values="0.5"/>')

    result = ColorMatrixFilter().apply(primitive, _context(enable_native_color_transforms=True))

    assert result.fallback == "bitmap"
    assert result.metadata.get("blip_color_transforms") == [{"tag": "satMod", "val": 50000}]


def test_color_matrix_hue_rotate_records_blip_transform_candidates() -> None:
    primitive = etree.fromstring('<feColorMatrix type="hueRotate" values="90"/>')

    result = ColorMatrixFilter().apply(primitive, _context(enable_native_color_transforms=True))

    assert result.fallback == "bitmap"
    assert result.metadata.get("blip_color_transforms") == [{"tag": "hueOff", "val": 5400000}]


def test_component_transfer_alpha_linear_records_blip_transform_candidates() -> None:
    primitive = etree.fromstring(
        "<feComponentTransfer><feFuncA type='linear' slope='0.4' intercept='0'/></feComponentTransfer>"
    )

    result = ComponentTransferFilter().apply(primitive, _context(enable_native_color_transforms=True))

    assert result.fallback == "emf"
    assert result.metadata.get("blip_color_transforms") == [{"tag": "alphaModFix", "amt": 40000}]


def test_component_transfer_ignores_blip_transform_candidates_when_disabled() -> None:
    primitive = etree.fromstring(
        "<feComponentTransfer><feFuncA type='linear' slope='0.4' intercept='0'/></feComponentTransfer>"
    )

    result = ComponentTransferFilter().apply(primitive, _context(enable_native_color_transforms=False))

    assert result.fallback == "emf"
    assert "blip_color_transforms" not in result.metadata
