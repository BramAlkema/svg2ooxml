from __future__ import annotations

from lxml import etree

from svg2ooxml.drawingml.xml_builder import NS_A
from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.primitives.composite import CompositeFilter


def _context(
    pipeline: dict[str, FilterResult],
    *,
    options: dict[str, object] | None = None,
) -> FilterContext:
    return FilterContext(
        filter_element=etree.Element("filter"),
        pipeline_state=pipeline,
        options=options or {},
    )


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


def test_composite_mask_approximates_solid_metadata() -> None:
    pipeline = {
        "SourceGraphic": FilterResult(success=True, drawingml="<a:effectLst><a:fill/></a:effectLst>", metadata={}),
        "mask": FilterResult(
            success=True,
            drawingml="",
            metadata={"fill": {"type": "solid", "rgb": "00FF00", "opacity": 0.4}},
        ),
    }
    primitive = etree.fromstring('<feComposite operator="in" in="SourceGraphic" in2="mask"/>')

    result = CompositeFilter().apply(primitive, _context(pipeline))

    assert "<a:solidFill>" in result.drawingml
    assert result.metadata.get("mask_approximation") == "solid_mask"
    assert result.fallback is None


def test_composite_mask_approximates_gradient_metadata() -> None:
    pipeline = {
        "SourceGraphic": FilterResult(success=True, drawingml="<a:effectLst><a:fill/></a:effectLst>", metadata={}),
        "mask": FilterResult(
            success=True,
            drawingml="",
            metadata={
                "fill": {
                    "type": "linearGradient",
                    "stops": [
                        {"offset": 0.0, "rgb": "000000", "opacity": 0.2},
                        {"offset": 1.0, "rgb": "FFFFFF", "opacity": 0.8},
                    ],
                }
            },
        ),
    }
    primitive = etree.fromstring('<feComposite operator="in" in="SourceGraphic" in2="mask"/>')

    result = CompositeFilter().apply(primitive, _context(pipeline))

    assert "<a:solidFill>" in result.drawingml
    assert result.metadata.get("mask_approximation") == "gradient_mask_avg"
    assert result.fallback is None


def test_composite_mask_flattens_multiple_effect_lists() -> None:
    pipeline = {
        "SourceGraphic": FilterResult(success=True, drawingml="<a:effectLst><a:fill/></a:effectLst>", metadata={}),
        "mask": FilterResult(
            success=True,
            drawingml=(
                "<a:effectLst><a:blur/></a:effectLst>"
                "<a:effectLst><a:glow/></a:effectLst>"
            ),
            metadata={"native_support": True},
        ),
    }
    primitive = etree.fromstring('<feComposite operator="in" in="SourceGraphic" in2="mask"/>')

    result = CompositeFilter().apply(primitive, _context(pipeline))

    root = etree.fromstring(f'<root xmlns:a="{NS_A}">{result.drawingml}</root>'.encode())
    alpha = root.find(".//a:alphaModFix", namespaces={"a": NS_A})
    assert alpha is not None
    inner = alpha.find("a:effectLst", namespaces={"a": NS_A})
    assert inner is not None
    tags = [child.tag.split("}", 1)[1] for child in inner if isinstance(child.tag, str)]
    assert tags == ["blur", "glow"]


def test_composite_mask_uses_effect_dag_when_policy_enabled() -> None:
    pipeline = {
        "SourceGraphic": FilterResult(success=True, drawingml="<a:effectLst><a:fill/></a:effectLst>", metadata={}),
        "mask": FilterResult(
            success=True,
            drawingml="<a:effectLst><a:blur/></a:effectLst>",
            metadata={"native_support": True},
        ),
    }
    primitive = etree.fromstring('<feComposite operator="in" in="SourceGraphic" in2="mask"/>')

    result = CompositeFilter().apply(
        primitive,
        _context(pipeline, options={"policy": {"enable_effect_dag": True}}),
    )

    assert result.fallback is None
    assert result.drawingml.startswith("<a:effectDag")
    assert "<a:cont/>" in result.drawingml
    assert "<a:alphaModFix>" in result.drawingml
