from __future__ import annotations

import pytest

from svg2ooxml.core.pptx_exporter import SvgToPptxExporter
from svg2ooxml.core.tracing import ConversionTracer
from svg2ooxml.ir.paint import LinearGradientPaint
from svg2ooxml.ir.scene import Group
from svg2ooxml.ir.shapes import Rectangle


def _render_result(svg: str):
    return SvgToPptxExporter()._render_svg(svg, ConversionTracer())  # type: ignore[attr-defined]


def _render(svg: str):
    return _render_result(svg)[1]


def _flatten(elements):
    for element in elements:
        yield element
        if isinstance(element, Group):
            yield from _flatten(element.children)


def _rectangle_with_id(elements, element_id: str) -> Rectangle:
    return next(
        element
        for element in _flatten(elements)
        if isinstance(element, Rectangle)
        and element_id in getattr(element, "metadata", {}).get("element_ids", [])
    )


def test_nested_svg_viewport_scales_child_geometry() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
      <svg x="10" y="20" width="50" height="50" viewBox="0 0 1000 1000">
        <rect id="cell" x="100" y="200" width="100" height="100" fill="#000000"/>
      </svg>
    </svg>
    """

    scene = _render(svg)

    cell = _rectangle_with_id(scene.elements, "cell")

    assert cell.bbox.x == pytest.approx(15.0)
    assert cell.bbox.y == pytest.approx(30.0)
    assert cell.bbox.width == pytest.approx(5.0)
    assert cell.bbox.height == pytest.approx(5.0)


def test_nested_svg_percent_viewport_resolves_against_parent_viewport() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
      <svg x="10%" y="20%" width="50%" height="50%" viewBox="0 0 100 100">
        <rect id="cell" x="50" y="50" width="10" height="10" fill="#000000"/>
      </svg>
    </svg>
    """

    scene = _render(svg)

    cell = _rectangle_with_id(scene.elements, "cell")
    assert cell.bbox.x == pytest.approx(35.0)
    assert cell.bbox.y == pytest.approx(45.0)
    assert cell.bbox.width == pytest.approx(5.0)
    assert cell.bbox.height == pytest.approx(5.0)


def test_nested_svg_viewport_scales_use_geometry() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         width="100" height="100" viewBox="0 0 100 100">
      <defs>
        <rect id="base" width="100" height="100" fill="#000000"/>
      </defs>
      <svg x="10" y="20" width="50" height="50" viewBox="0 0 1000 1000">
        <use id="cell" href="#base" xlink:href="#base" x="100" y="200"/>
      </svg>
    </svg>
    """

    scene = _render(svg)

    cell = _rectangle_with_id(scene.elements, "cell")
    assert cell.bbox.x == pytest.approx(15.0)
    assert cell.bbox.y == pytest.approx(30.0)
    assert cell.bbox.width == pytest.approx(5.0)
    assert cell.bbox.height == pytest.approx(5.0)


def test_use_opacity_multiplies_source_opacity() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         width="20" height="20">
      <defs>
        <rect id="source" width="10" height="10" fill="#000000" opacity="0.5"/>
      </defs>
      <use id="instance" href="#source" xlink:href="#source" opacity="0.5"/>
    </svg>
    """

    scene = _render(svg)

    instance = _rectangle_with_id(scene.elements, "instance")
    assert instance.opacity == pytest.approx(0.25)


def test_use_fill_none_overrides_default_referenced_fill() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         width="20" height="20">
      <defs>
        <rect id="source" width="10" height="10"/>
      </defs>
      <use id="instance" href="#source" xlink:href="#source" fill="none"/>
    </svg>
    """

    _, scene = _render_result(svg)

    instance = _rectangle_with_id(scene.elements, "instance")
    assert instance.fill is None


def test_use_fill_opacity_applies_to_referenced_fill() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         width="20" height="20">
      <defs>
        <rect id="source" width="10" height="10" fill="#0000ff"/>
      </defs>
      <use id="instance" href="#source" xlink:href="#source" fill-opacity="0.5"/>
    </svg>
    """

    render_result, scene = _render_result(svg)

    instance = _rectangle_with_id(scene.elements, "instance")
    assert instance.fill is not None
    assert instance.fill.opacity == pytest.approx(0.5)
    assert '<a:alpha val="50000"/>' in render_result.slide_xml


def test_use_stroke_opacity_applies_without_use_stroke_paint() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         width="20" height="20">
      <defs>
        <rect id="source" width="10" height="10" fill="none"
              stroke="#000000" stroke-width="2"/>
      </defs>
      <use id="instance" href="#source" xlink:href="#source" stroke-opacity="0.5"/>
    </svg>
    """

    render_result, scene = _render_result(svg)

    instance = _rectangle_with_id(scene.elements, "instance")
    assert instance.stroke is not None
    assert instance.stroke.paint.opacity == pytest.approx(1.0)
    assert instance.stroke.opacity == pytest.approx(0.5)
    assert '<a:alpha val="50000"/>' in render_result.slide_xml
    assert '<a:alpha val="25000"/>' not in render_result.slide_xml


def test_direct_shape_opacity_is_local_and_emitted_once() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">
      <rect id="shape" width="10" height="10" fill="#000000" opacity="0.5"/>
    </svg>
    """

    render_result, scene = _render_result(svg)

    shape = _rectangle_with_id(scene.elements, "shape")
    assert shape.opacity == pytest.approx(0.5)
    assert '<a:alpha val="50000"/>' in render_result.slide_xml


def test_direct_stroke_opacity_is_emitted_once() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">
      <rect id="shape" width="10" height="10" fill="none"
            stroke="#000000" stroke-width="2" stroke-opacity="0.5"/>
    </svg>
    """

    render_result, scene = _render_result(svg)

    shape = _rectangle_with_id(scene.elements, "shape")
    assert shape.stroke is not None
    assert shape.stroke.paint.opacity == pytest.approx(1.0)
    assert shape.stroke.opacity == pytest.approx(0.5)
    assert '<a:alpha val="50000"/>' in render_result.slide_xml
    assert '<a:alpha val="25000"/>' not in render_result.slide_xml


def test_parent_fill_opacity_is_inherited_by_child_paint() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">
      <g fill-opacity="0.5">
        <rect id="child" width="10" height="10" fill="#0000ff"/>
      </g>
    </svg>
    """

    render_result, scene = _render_result(svg)

    child = _rectangle_with_id(scene.elements, "child")
    assert child.fill is not None
    assert child.fill.opacity == pytest.approx(0.5)
    assert '<a:alpha val="50000"/>' in render_result.slide_xml


def test_parent_fill_opacity_is_inherited_by_gradient_stops() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">
      <defs>
        <linearGradient id="grad">
          <stop offset="0" stop-color="#000000"/>
          <stop offset="1" stop-color="#ffffff"/>
        </linearGradient>
      </defs>
      <g fill-opacity="0.5">
        <rect id="child" width="10" height="10" fill="url(#grad)"/>
      </g>
    </svg>
    """

    _, scene = _render_result(svg)

    child = _rectangle_with_id(scene.elements, "child")
    assert isinstance(child.fill, LinearGradientPaint)
    assert [stop.opacity for stop in child.fill.stops] == pytest.approx([0.5, 0.5])


def test_gradient_stops_resolve_css_color_syntax_and_percent_opacity() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">
      <defs>
        <linearGradient id="grad">
          <stop offset="0" stop-color="red" stop-opacity="50%"/>
          <stop offset="1" style="stop-color: rgb(0 0 255 / 75%); stop-opacity: 25%"/>
        </linearGradient>
      </defs>
      <rect id="child" width="10" height="10" fill="url(#grad)"/>
    </svg>
    """

    _, scene = _render_result(svg)

    child = _rectangle_with_id(scene.elements, "child")
    assert isinstance(child.fill, LinearGradientPaint)
    assert [stop.rgb for stop in child.fill.stops] == ["FF0000", "0000FF"]
    assert [stop.opacity for stop in child.fill.stops] == pytest.approx([0.5, 0.1875])


def test_parent_group_opacity_is_not_inherited_by_child() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">
      <g id="group" opacity="0.5">
        <rect id="child" width="10" height="10" fill="#000000"/>
      </g>
    </svg>
    """

    render_result, scene = _render_result(svg)

    group = next(element for element in scene.elements if isinstance(element, Group))
    child = _rectangle_with_id(scene.elements, "child")
    assert group.opacity == pytest.approx(0.5)
    assert child.opacity == pytest.approx(1.0)
    assert '<a:alpha val="50000"/>' in render_result.slide_xml
    assert '<a:alpha val="25000"/>' not in render_result.slide_xml


def test_used_group_opacity_stays_on_group_not_children() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         width="20" height="20">
      <defs>
        <g id="source-group" opacity="0.5">
          <rect id="child" width="10" height="10" fill="#000000"/>
        </g>
      </defs>
      <use id="instance" href="#source-group" xlink:href="#source-group"/>
    </svg>
    """

    scene = _render(svg)

    group = next(element for element in scene.elements if isinstance(element, Group))
    child = _rectangle_with_id(scene.elements, "child")
    assert group.opacity == pytest.approx(0.5)
    assert child.opacity == pytest.approx(1.0)
    assert getattr(child.fill, "opacity", 1.0) == pytest.approx(1.0)


def test_used_group_opacity_survives_flattening_in_pptx() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         width="20" height="20">
      <defs>
        <g id="source-group" opacity="0.5">
          <rect id="child" width="10" height="10" fill="#000000"/>
        </g>
      </defs>
      <use id="instance" href="#source-group" xlink:href="#source-group"/>
    </svg>
    """

    render_result, _scene = _render_result(svg)

    assert "<p:grpSp>" not in render_result.slide_xml
    assert '<a:alpha val="50000"/>' in render_result.slide_xml


def test_used_group_preserves_child_opacity_and_source_id() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         width="20" height="20">
      <defs>
        <g id="source-group">
          <rect id="child" width="10" height="10" fill="#000000" opacity="0.2"/>
        </g>
      </defs>
      <use id="instance" href="#source-group" xlink:href="#source-group"/>
    </svg>
    """

    scene = _render(svg)

    child = _rectangle_with_id(scene.elements, "child")
    assert child.opacity == pytest.approx(0.2)
    assert "instance" in child.metadata.get("element_ids", [])


def test_use_stroke_dash_offset_zero_overrides_source_offset() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         width="20" height="20">
      <defs>
        <rect id="source" width="10" height="10" fill="none"
              stroke="#000000" stroke-width="1"
              stroke-dasharray="3 2" stroke-dashoffset="4"/>
      </defs>
      <use id="instance" href="#source" xlink:href="#source"
           stroke="#000000" stroke-width="1"
           stroke-dasharray="3 2" stroke-dashoffset="0"/>
    </svg>
    """

    scene = _render(svg)

    instance = _rectangle_with_id(scene.elements, "instance")
    assert instance.stroke is not None
    assert instance.stroke.dash_offset == pytest.approx(0.0)


def test_use_stroke_dasharray_none_clears_source_dashes() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         width="20" height="20">
      <defs>
        <rect id="source" width="10" height="10" fill="none"
              stroke="#000000" stroke-width="1"
              stroke-dasharray="3 2" stroke-dashoffset="4"/>
      </defs>
      <use id="instance" href="#source" xlink:href="#source"
           stroke="#000000" stroke-width="1"
           stroke-dasharray="none" stroke-dashoffset="0"/>
    </svg>
    """

    scene = _render(svg)

    instance = _rectangle_with_id(scene.elements, "instance")
    assert instance.stroke is not None
    assert instance.stroke.dash_array is None
    assert instance.stroke.dash_offset == pytest.approx(0.0)


def test_unresolved_resvg_stroke_override_keeps_runtime_stroke(monkeypatch) -> None:
    from svg2ooxml.paint import resvg_bridge

    monkeypatch.setattr(
        resvg_bridge,
        "resolve_stroke_style",
        lambda _stroke, _tree: None,
    )
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">
      <rect id="shape" width="10" height="10" fill="none"
            stroke="#123456" stroke-width="2"/>
    </svg>
    """

    scene = _render(svg)

    shape = _rectangle_with_id(scene.elements, "shape")
    assert shape.stroke is not None
    assert getattr(shape.stroke.paint, "rgb", None) == "123456"
    assert shape.stroke.width == pytest.approx(2.0)


def test_used_group_clip_stays_on_wrapper_not_child() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         width="20" height="20">
      <defs>
        <clipPath id="clip">
          <rect x="0" y="0" width="5" height="10"/>
        </clipPath>
        <g id="source-group" clip-path="url(#clip)">
          <rect id="child" width="10" height="10" fill="#000000"/>
        </g>
      </defs>
      <use id="instance" href="#source-group" xlink:href="#source-group"/>
    </svg>
    """

    scene = _render(svg)

    group = next(element for element in scene.elements if isinstance(element, Group))
    child = _rectangle_with_id(scene.elements, "child")
    assert group.clip is not None
    assert getattr(child, "clip", None) is None


def test_used_group_clip_bounds_survive_flattening_in_pptx() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         width="20" height="20">
      <defs>
        <clipPath id="clip">
          <rect x="0" y="0" width="5" height="10"/>
        </clipPath>
        <g id="source-group" clip-path="url(#clip)">
          <rect id="child" width="10" height="10" fill="#000000"/>
        </g>
      </defs>
      <use id="instance" href="#source-group" xlink:href="#source-group"/>
    </svg>
    """

    render_result, _scene = _render_result(svg)

    assert "<p:grpSp>" not in render_result.slide_xml
    assert 'cx="47625"' in render_result.slide_xml
    assert 'cy="95250"' in render_result.slide_xml


def test_use_reference_href_is_not_treated_as_bookmark_navigation() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         width="20" height="20">
      <defs>
        <rect id="source" width="10" height="10" fill="#000000"/>
      </defs>
      <use id="instance" href="#source" xlink:href="#source"/>
    </svg>
    """

    render_result, scene = _render_result(svg)

    instance = _rectangle_with_id(scene.elements, "instance")
    assert "navigation" not in instance.metadata
    assert "hlinkClick" not in render_result.slide_xml
    assert not list(render_result.assets.iter_navigation())


def test_anchor_navigation_survives_used_group_flattening() -> None:
    svg = """
    <svg xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         width="20" height="20">
      <defs>
        <g id="source-group">
          <rect id="child" width="10" height="10" fill="#000000"/>
        </g>
      </defs>
      <a href="https://example.com">
        <use id="instance" href="#source-group" xlink:href="#source-group"/>
      </a>
    </svg>
    """

    render_result, _scene = _render_result(svg)

    assert "hlinkClick" in render_result.slide_xml
    assert [
        asset
        for asset in render_result.assets.iter_navigation()
        if asset.target == "https://example.com"
    ]
