"""Integration tests for stroke width propagation through resvg."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from svg2ooxml.core.pptx_exporter import SvgToPptxExporter
from svg2ooxml.core.tracing import ConversionTracer


def _iter_shapes(elements: Iterable) -> Iterable:
    """Yield shapes recursively from a list of IR elements."""
    stack: list = list(elements)
    while stack:
        shape = stack.pop()
        yield shape
        children = getattr(shape, "children", None)
        if children:
            stack.extend(children)


@pytest.mark.integration
def test_use_elements_retain_stroke_width_via_resvg() -> None:
    """Ensure <use> clones keep their stroke width after resvg conversion."""
    svg_path = Path("tests/svg/struct-use-10-f.svg")
    svg_text = svg_path.read_text(encoding="utf-8")

    exporter = SvgToPptxExporter(geometry_mode="resvg")
    tracer = ConversionTracer()
    _, scene = exporter._render_svg(svg_text, tracer)
    assert hasattr(scene, "elements")

    target_ids = {"testid1", "testid2", "testid3"}
    observed = {}

    for shape in _iter_shapes(scene.elements):
        stroke = getattr(shape, "stroke", None)
        if stroke is None:
            continue

        metadata = getattr(shape, "metadata", None)
        element_ids: set[str] = set()

        if isinstance(metadata, dict):
            ids = metadata.get("element_ids")
            if isinstance(ids, (list, tuple)):
                element_ids.update(str(value) for value in ids)
            element_id = metadata.get("element_id")
            if isinstance(element_id, str):
                element_ids.add(element_id)

        attr_id = getattr(shape, "element_id", None)
        if isinstance(attr_id, str):
            element_ids.add(attr_id)

        for element_id in element_ids:
            if element_id in target_ids:
                observed[element_id] = stroke.width

    assert set(observed.keys()) == target_ids
    for width in observed.values():
        assert width == pytest.approx(10.0)
