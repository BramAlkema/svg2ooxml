from __future__ import annotations

from lxml import etree

from svg2ooxml.filters.base import FilterContext, FilterResult
from svg2ooxml.filters.registry import FilterRegistry


def test_seed_base_inputs_includes_filter_inputs_metadata() -> None:
    registry = FilterRegistry()
    filter_element = etree.Element("filter")
    context = FilterContext(
        filter_element=filter_element,
        options={
            "filter_inputs": {
                "SourceGraphic": {
                    "geometry": [
                        {"type": "line", "start": (0.0, 0.0), "end": (10.0, 0.0)}
                    ],
                    "closed": False,
                    "fill": {"type": "solid", "rgb": "FF0000", "opacity": 1.0},
                }
            }
        },
    )
    pipeline: dict[str, FilterResult] = {}

    registry._seed_base_inputs(pipeline, context)

    assert "SourceGraphic" in pipeline
    assert "SourceAlpha" in pipeline

    graphic_meta = pipeline["SourceGraphic"].metadata
    assert graphic_meta["ref"] == "SourceGraphic"
    assert graphic_meta["geometry"][0]["type"] == "line"
    assert graphic_meta["fill"]["type"] == "solid"

    alpha_meta = pipeline["SourceAlpha"].metadata
    assert alpha_meta["ref"] == "SourceAlpha"
    assert alpha_meta["alpha_source"] == "SourceGraphic"
    assert alpha_meta["geometry"][0]["type"] == "line"
