from __future__ import annotations

from lxml import etree

from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.primitives.blend import BlendFilter


def _context_with_pipeline(pipeline: dict[str, FilterResult]) -> FilterContext:
    filter_element = etree.Element("filter")
    return FilterContext(filter_element=filter_element, pipeline_state=pipeline)


def test_blend_normal_merges_effect_lists() -> None:
    pipeline = {
        "SourceGraphic": FilterResult(success=True, drawingml="<a:effectLst><a:fill/></a:effectLst>", metadata={}),
        "flood1": FilterResult(success=True, drawingml="<a:effectLst><a:solidFill/></a:effectLst>", metadata={}),
    }
    context = _context_with_pipeline(pipeline)
    primitive = etree.fromstring('<feBlend mode="normal" in="SourceGraphic" in2="flood1"/>')

    result = BlendFilter().apply(primitive, context)

    assert result.drawingml == "<a:effectLst><a:fill/><a:solidFill/></a:effectLst>"
    assert result.fallback is None
    assert result.metadata.get("native_support") is True


def test_blend_multiply_uses_fill_overlay_when_flood_metadata() -> None:
    pipeline = {
        "SourceGraphic": FilterResult(success=True, drawingml="<a:effectLst><a:fill/></a:effectLst>", metadata={}),
        "layer": FilterResult(
            success=True,
            drawingml="",
            metadata={"flood_color": "008000", "flood_opacity": 0.5},
        ),
    }
    context = _context_with_pipeline(pipeline)
    primitive = etree.fromstring('<feBlend mode="multiply" in="SourceGraphic" in2="layer"/>')

    result = BlendFilter().apply(primitive, context)

    expected_overlay = (
        "<a:effectLst><a:fill/>"
        '<a:fillOverlay blend="mult">'
        '<a:solidFill><a:srgbClr val="008000"><a:alpha val="50000"/></a:srgbClr></a:solidFill>'
        "</a:fillOverlay></a:effectLst>"
    )
    assert result.drawingml == expected_overlay
    assert result.fallback is None
    assert result.metadata.get("native_support") is True
