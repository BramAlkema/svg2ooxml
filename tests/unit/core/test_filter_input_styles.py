from __future__ import annotations

import pytest

from svg2ooxml.core.pptx_exporter import SvgToPptxExporter
from svg2ooxml.core.tracing import ConversionTracer
from svg2ooxml.ir.scene import Group


def _render(svg: str):
    return SvgToPptxExporter()._render_svg(svg, ConversionTracer())[1]  # type: ignore[attr-defined]


def _flatten(elements):
    for element in elements:
        yield element
        if isinstance(element, Group):
            yield from _flatten(element.children)


def test_filtered_group_children_keep_inherited_stroke_dasharray() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
      <defs>
        <filter id="blur"><feGaussianBlur in="SourceGraphic" stdDeviation="2"/></filter>
      </defs>
      <g stroke="#000000" stroke-width="3" stroke-dasharray="25 5">
        <g id="target" filter="url(#blur)" fill="red">
          <circle cx="50" cy="50" r="20"/>
        </g>
      </g>
    </svg>
    """

    scene = _render(svg)

    filtered_group = next(
        element
        for element in _flatten(scene.elements)
        if isinstance(element, Group)
        and any(
            entry.get("id") == "blur"
            for entry in getattr(element, "metadata", {}).get("filters", [])
        )
    )
    circle = filtered_group.children[0]

    assert circle.stroke is not None
    assert circle.stroke.dash_array == pytest.approx([25.0, 5.0])


def test_empty_filtered_group_survives_for_background_filter() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
      <defs>
        <filter id="shift" filterUnits="userSpaceOnUse" x="0" y="0" width="100" height="100">
          <feOffset in="BackgroundImage" dy="10"/>
        </filter>
      </defs>
      <rect x="10" y="10" width="20" height="20" fill="red"/>
      <g id="empty-filter" filter="url(#shift)"/>
    </svg>
    """

    scene = _render(svg)

    filtered_group = next(
        element
        for element in _flatten(scene.elements)
        if isinstance(element, Group)
        and any(
            entry.get("id") == "shift"
            for entry in getattr(element, "metadata", {}).get("filters", [])
        )
    )

    assert filtered_group.children == []
