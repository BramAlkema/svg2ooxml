from __future__ import annotations

from lxml import etree

from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.primitives.composite import CompositeFilter


def _context(pipeline: dict[str, FilterResult]) -> FilterContext:
    return FilterContext(filter_element=etree.Element("filter"), pipeline_state=pipeline)


def test_composite_over_concatenates_effect_lists() -> None:
    pipeline = {
        "SourceGraphic": FilterResult(success=True, drawingml="<a:effectLst><a:fill/></a:effectLst>", metadata={}),
        "blurResult": FilterResult(success=True, drawingml="<a:effectLst><a:outerShdw/></a:effectLst>", metadata={}),
    }
    primitive = etree.fromstring('<feComposite operator="over" in="blurResult" in2="SourceGraphic"/>')

    result = CompositeFilter().apply(primitive, _context(pipeline))

    assert result.drawingml == "<a:effectLst><a:outerShdw/><a:fill/></a:effectLst>"
    assert result.fallback is None
    assert result.metadata.get("native_support") is True


def test_composite_mask_wraps_non_effect_list() -> None:
    pipeline = {
        "SourceGraphic": FilterResult(success=True, drawingml="<a:effectLst><a:fill/></a:effectLst>", metadata={}),
        "mask": FilterResult(
            success=True,
            drawingml="<a:outerShdw/>",
            metadata={"native_support": True},
        ),
    }
    primitive = etree.fromstring('<feComposite operator="in" in="SourceGraphic" in2="mask"/>')

    result = CompositeFilter().apply(primitive, _context(pipeline))

    assert result.drawingml.startswith("<a:effectLst")
    assert result.fallback is None
    assert result.metadata.get("native_support") is True
