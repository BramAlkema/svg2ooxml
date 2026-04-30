from __future__ import annotations

import base64
from types import SimpleNamespace

import numpy as np
import pytest

from svg2ooxml.core.resvg.parser.presentation import Presentation
from svg2ooxml.core.resvg.usvg_tree import FilterNode, FilterPrimitive
from svg2ooxml.render.filters import apply_filter, plan_filter
from svg2ooxml.render.filters_lighting import light_direction
from svg2ooxml.render.filters_region import parse_user_length
from svg2ooxml.render.rasterizer import Viewport
from svg2ooxml.render.surface import Surface


def _empty_presentation() -> Presentation:
    return Presentation(
        fill=None,
        stroke=None,
        stroke_width=None,
        stroke_dasharray=None,
        stroke_dashoffset=None,
        stroke_linecap=None,
        stroke_linejoin=None,
        stroke_miterlimit=None,
        fill_opacity=None,
        stroke_opacity=None,
        opacity=None,
        transform=None,
        font_family=None,
        font_size=None,
        font_style=None,
        font_weight=None,
    )


def _make_filter_node(primitives: list[FilterPrimitive]) -> FilterNode:
    return FilterNode(
        tag="filter",
        id="test-filter",
        presentation=_empty_presentation(),
        attributes={},
        styles={},
        children=[],
        primitives=tuple(primitives),
        filter_units="objectBoundingBox",
        primitive_units="userSpaceOnUse",
    )


def _rect_descriptor(
    *,
    fill: dict[str, object] | None = None,
    stroke: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "shape_type": "Rectangle",
        "geometry": [
            {"type": "line", "start": (0.0, 0.0), "end": (10.0, 0.0)},
            {"type": "line", "start": (10.0, 0.0), "end": (10.0, 10.0)},
            {"type": "line", "start": (10.0, 10.0), "end": (0.0, 10.0)},
            {"type": "line", "start": (0.0, 10.0), "end": (0.0, 0.0)},
        ],
        "closed": True,
        "fill": fill,
        "stroke": stroke,
        "opacity": 1.0,
        "bbox": {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0},
    }


def _paint_input_options() -> dict[str, object]:
    return {
        "filter_inputs": {
            "FillPaint": _rect_descriptor(
                fill={"type": "solid", "rgb": "FF0000", "opacity": 1.0}
            ),
            "StrokePaint": _rect_descriptor(
                stroke={
                    "width": 2.0,
                    "paint": {"type": "solid", "rgb": "0000FF", "opacity": 1.0},
                    "join": "miter",
                    "cap": "butt",
                    "miter_limit": 4.0,
                    "dash_array": None,
                    "dash_offset": 0.0,
                    "opacity": 1.0,
                }
            ),
        }
    }


def _linear_gradient_descriptor() -> dict[str, object]:
    return {
        "type": "linearGradient",
        "stops": [
            {"offset": 0.0, "rgb": "FF0000", "opacity": 1.0},
            {"offset": 1.0, "rgb": "0000FF", "opacity": 1.0},
        ],
        "start": (0.0, 0.5),
        "end": (1.0, 0.5),
        "gradient_units": "objectBoundingBox",
        "spread_method": "pad",
    }


def test_plan_filter_rejects_unsupported_primitive() -> None:
    primitive = FilterPrimitive(
        tag="feDropShadow",
        attributes={"result": "shadow"},
        styles={},
    )
    filter_node = _make_filter_node([primitive])

    plan = plan_filter(filter_node)

    assert plan is None


def test_plan_filter_accepts_declared_fill_paint_input() -> None:
    blur = FilterPrimitive(
        tag="feGaussianBlur",
        attributes={"in": "FillPaint", "stdDeviation": "0"},
        styles={},
    )
    filter_node = _make_filter_node([blur])

    plan = plan_filter(filter_node, options=_paint_input_options())

    assert plan is not None
    assert plan.primitives[0].inputs == ("FillPaint",)
    assert "FillPaint" in plan.input_descriptors


def test_plan_filter_derives_fill_paint_input_from_source_graphic() -> None:
    blur = FilterPrimitive(
        tag="feGaussianBlur",
        attributes={"in": "FillPaint", "stdDeviation": "0"},
        styles={},
    )
    filter_node = _make_filter_node([blur])

    plan = plan_filter(
        filter_node,
        options={
            "filter_inputs": {
                "SourceGraphic": _rect_descriptor(
                    fill={"type": "solid", "rgb": "FF0000", "opacity": 1.0},
                    stroke={
                        "width": 2.0,
                        "paint": {"type": "solid", "rgb": "0000FF", "opacity": 1.0},
                    },
                )
            }
        },
    )

    assert plan is not None
    assert plan.input_descriptors["FillPaint"]["stroke"] is None


def test_plan_filter_rejects_undeclared_fill_paint_input() -> None:
    blur = FilterPrimitive(
        tag="feGaussianBlur",
        attributes={"in": "FillPaint", "stdDeviation": "0"},
        styles={},
    )
    filter_node = _make_filter_node([blur])

    assert plan_filter(filter_node) is None


def test_apply_filter_uses_declared_fill_paint_surface() -> None:
    pytest.importorskip("skia")

    blur = FilterPrimitive(
        tag="feGaussianBlur",
        attributes={"in": "FillPaint", "stdDeviation": "0"},
        styles={},
    )
    filter_node = _make_filter_node([blur])
    plan = plan_filter(filter_node, options=_paint_input_options())
    assert plan is not None

    surface = Surface.make(10, 10)
    viewport = Viewport(
        width=10, height=10, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result = apply_filter(surface, plan, (0.0, 0.0, 10.0, 10.0), viewport)

    center = result.data[5, 5]
    assert center[0] > 0.8
    assert center[1] < 0.05
    assert center[2] < 0.05
    assert center[3] > 0.8


def test_apply_filter_uses_declared_stroke_paint_surface() -> None:
    pytest.importorskip("skia")

    blur = FilterPrimitive(
        tag="feGaussianBlur",
        attributes={"in": "StrokePaint", "stdDeviation": "0"},
        styles={},
    )
    filter_node = _make_filter_node([blur])
    plan = plan_filter(filter_node, options=_paint_input_options())
    assert plan is not None

    surface = Surface.make(10, 10)
    viewport = Viewport(
        width=10, height=10, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result = apply_filter(surface, plan, (0.0, 0.0, 10.0, 10.0), viewport)

    edge = result.data[0, 5]
    center = result.data[5, 5]
    assert edge[2] > 0.4
    assert edge[3] > 0.4
    assert center[3] < 0.05


def test_apply_filter_uses_declared_gradient_paint_surfaces() -> None:
    pytest.importorskip("skia")

    fill_blur = FilterPrimitive(
        tag="feGaussianBlur",
        attributes={"in": "FillPaint", "stdDeviation": "0"},
        styles={},
    )
    fill_node = _make_filter_node([fill_blur])
    gradient = _linear_gradient_descriptor()
    fill_plan = plan_filter(
        fill_node,
        options={"filter_inputs": {"FillPaint": _rect_descriptor(fill=gradient)}},
    )
    assert fill_plan is not None

    surface = Surface.make(10, 10)
    viewport = Viewport(
        width=10, height=10, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    fill_result = apply_filter(surface, fill_plan, (0.0, 0.0, 10.0, 10.0), viewport)

    left = fill_result.data[5, 2]
    right = fill_result.data[5, 8]
    assert left[0] > left[2]
    assert right[2] > right[0]
    assert left[3] > 0.8
    assert right[3] > 0.8

    stroke_blur = FilterPrimitive(
        tag="feGaussianBlur",
        attributes={"in": "StrokePaint", "stdDeviation": "0"},
        styles={},
    )
    stroke_node = _make_filter_node([stroke_blur])
    stroke_plan = plan_filter(
        stroke_node,
        options={
            "filter_inputs": {
                "StrokePaint": _rect_descriptor(
                    stroke={
                        "width": 2.0,
                        "paint": gradient,
                        "join": "miter",
                        "cap": "butt",
                        "miter_limit": 4.0,
                        "dash_array": None,
                        "dash_offset": 0.0,
                        "opacity": 1.0,
                    }
                )
            }
        },
    )
    assert stroke_plan is not None

    stroke_result = apply_filter(
        surface,
        stroke_plan,
        (0.0, 0.0, 10.0, 10.0),
        viewport,
    )

    stroke_left = stroke_result.data[0, 2]
    stroke_right = stroke_result.data[0, 8]
    assert stroke_left[0] > stroke_left[2]
    assert stroke_right[2] > stroke_right[0]
    assert stroke_left[3] > 0.2
    assert stroke_right[3] > 0.2


def test_apply_filter_uses_provided_background_input_surface() -> None:
    blur = FilterPrimitive(
        tag="feGaussianBlur",
        attributes={"in": "BackgroundImage", "stdDeviation": "0"},
        styles={},
    )
    filter_node = _make_filter_node([blur])
    plan = plan_filter(
        filter_node,
        options={"available_filter_inputs": ["BackgroundImage"]},
    )
    assert plan is not None
    assert plan.primitives[0].inputs == ("BackgroundImage",)

    source = Surface.make(4, 4)
    background = Surface.make(4, 4)
    background.data[..., 1] = 1.0
    background.data[..., 3] = 1.0
    viewport = Viewport(
        width=4, height=4, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result = apply_filter(
        source,
        plan,
        (0.0, 0.0, 4.0, 4.0),
        viewport,
        input_surfaces={"BackgroundImage": background},
    )

    pixel = result.data[2, 2]
    assert pixel[1] > 0.8
    assert pixel[0] < 0.05
    assert pixel[2] < 0.05
    assert pixel[3] > 0.8


def test_apply_filter_blend_lighten() -> None:
    flood = FilterPrimitive(
        tag="feFlood",
        attributes={"flood-color": "#0000ff", "result": "blue"},
        styles={},
    )
    blend = FilterPrimitive(
        tag="feBlend",
        attributes={"in": "SourceGraphic", "in2": "blue", "mode": "lighten"},
        styles={},
    )
    filter_node = _make_filter_node([flood, blend])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(4, 4)
    surface.data[..., 0] = 1.0  # red channel
    surface.data[..., 3] = 1.0  # alpha

    bounds = (0.0, 0.0, 4.0, 4.0)
    viewport = Viewport(
        width=4, height=4, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result = apply_filter(surface, plan, bounds, viewport)

    pixel = result.data[0, 0]
    np.testing.assert_allclose(
        pixel[:3], np.array([1.0, 0.0, 1.0]), rtol=1e-4, atol=1e-4
    )
    assert pixel[3] == pytest.approx(1.0)


def test_apply_filter_merge_layers() -> None:
    flood = FilterPrimitive(
        tag="feFlood",
        attributes={"flood-color": "#00ff00", "flood-opacity": "0.5", "result": "half"},
        styles={},
    )
    merge = FilterPrimitive(
        tag="feMerge",
        attributes={},
        styles={},
        children=(
            FilterPrimitive(
                tag="feMergeNode", attributes={"in": "SourceGraphic"}, styles={}
            ),
            FilterPrimitive(tag="feMergeNode", attributes={"in": "half"}, styles={}),
        ),
    )
    filter_node = _make_filter_node([flood, merge])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(2, 2)
    surface.data[..., 0] = 1.0
    surface.data[..., 3] = 1.0

    bounds = (0.0, 0.0, 2.0, 2.0)
    viewport = Viewport(
        width=2, height=2, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result = apply_filter(surface, plan, bounds, viewport)

    pixel = result.data[0, 0]
    np.testing.assert_allclose(
        pixel[:3], np.array([0.5, 0.5, 0.0]), rtol=1e-4, atol=1e-4
    )
    assert pixel[3] == pytest.approx(1.0)


def test_apply_filter_flood_accepts_percent_opacity() -> None:
    flood = FilterPrimitive(
        tag="feFlood",
        attributes={"flood-color": "#00ff00", "flood-opacity": "50%"},
        styles={},
    )
    filter_node = _make_filter_node([flood])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(2, 2)
    bounds = (0.0, 0.0, 2.0, 2.0)
    viewport = Viewport(
        width=2, height=2, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result = apply_filter(surface, plan, bounds, viewport)

    assert result.data[0, 0, 1] == pytest.approx(0.5)
    assert result.data[0, 0, 3] == pytest.approx(0.5)


def test_apply_filter_color_matrix_saturate_accepts_calc() -> None:
    color_matrix = FilterPrimitive(
        tag="feColorMatrix",
        attributes={"type": "saturate", "values": "calc(0.25 + 0.25)"},
        styles={},
    )
    filter_node = _make_filter_node([color_matrix])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(1, 1)
    surface.data[0, 0, :] = np.array([1.0, 0.0, 0.0, 1.0], dtype=np.float32)

    result = apply_filter(
        surface,
        plan,
        (0.0, 0.0, 1.0, 1.0),
        Viewport(width=1, height=1, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0),
    )

    np.testing.assert_allclose(
        result.data[0, 0, :3],
        np.array([0.6063, 0.1063, 0.1063], dtype=np.float32),
        atol=1e-4,
    )
    assert result.data[0, 0, 3] == pytest.approx(1.0)


def test_apply_filter_composite_arithmetic() -> None:
    flood_a = FilterPrimitive(
        tag="feFlood",
        attributes={"flood-color": "#ff0000", "result": "a"},
        styles={},
    )
    flood_b = FilterPrimitive(
        tag="feFlood",
        attributes={"flood-color": "#0000ff", "result": "b"},
        styles={},
    )
    composite = FilterPrimitive(
        tag="feComposite",
        attributes={
            "operator": "arithmetic",
            "in": "a",
            "in2": "b",
            "k1": "0",
            "k2": "0.25",
            "k3": "0.75",
            "k4": "0",
        },
        styles={},
    )
    filter_node = _make_filter_node([flood_a, flood_b, composite])
    plan = plan_filter(filter_node)
    assert plan is not None
    plan.primitives[-1].extra["k2"] = "calc(0.25)"
    plan.primitives[-1].extra["k3"] = "calc(0.5 + 0.25)"

    surface = Surface.make(2, 2)
    bounds = (0.0, 0.0, 2.0, 2.0)
    viewport = Viewport(
        width=2, height=2, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result = apply_filter(surface, plan, bounds, viewport)
    pixel = result.data[0, 0]
    np.testing.assert_allclose(
        pixel[:3], np.array([0.25, 0.0, 0.75], dtype=np.float32), atol=1e-6
    )
    assert pixel[3] == pytest.approx(1.0)


def test_apply_filter_component_transfer_linear_and_table() -> None:
    component = FilterPrimitive(
        tag="feComponentTransfer",
        attributes={"result": "adjusted"},
        styles={},
        children=(
            FilterPrimitive(
                tag="feFuncR", attributes={"type": "linear", "slope": "0.5"}, styles={}
            ),
            FilterPrimitive(tag="feFuncG", attributes={"type": "identity"}, styles={}),
            FilterPrimitive(
                tag="feFuncB",
                attributes={"type": "table", "tableValues": "0.0 0.5 1.0"},
                styles={},
            ),
        ),
    )
    filter_node = _make_filter_node([component])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(1, 1)
    surface.data[0, 0, :] = np.array([0.6, 0.4, 0.8, 1.0], dtype=np.float32)
    surface.data[0, 0, :3] *= surface.data[0, 0, 3]

    bounds = (0.0, 0.0, 1.0, 1.0)
    viewport = Viewport(
        width=1, height=1, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result = apply_filter(surface, plan, bounds, viewport)
    pixel = result.data[0, 0]
    np.testing.assert_allclose(
        pixel[:3], np.array([0.3, 0.4, 0.8], dtype=np.float32), atol=1e-3
    )
    assert pixel[3] == pytest.approx(1.0)


def test_plan_filter_accepts_convolve_matrix_edge_mode() -> None:
    convolve = FilterPrimitive(
        tag="feConvolveMatrix",
        attributes={
            "kernelMatrix": "0 0 0 0 1 0 0 0 0",
            "edgeMode": "wrap",
            "result": "convolved",
        },
        styles={},
    )
    filter_node = _make_filter_node([convolve])

    plan = plan_filter(filter_node)

    assert plan is not None
    primitive = plan.primitives[0]
    assert primitive.extra["edge_mode"] == "wrap"
    assert primitive.extra["order_x"] == 3
    assert primitive.extra["order_y"] == 3


def test_apply_filter_convolve_matrix_edge_modes_differ() -> None:
    def run(edge_mode: str) -> Surface:
        convolve = FilterPrimitive(
            tag="feConvolveMatrix",
            attributes={
                "kernelMatrix": "0 0 0 0 0 1 0 0 0",
                "edgeMode": edge_mode,
            },
            styles={},
        )
        filter_node = _make_filter_node([convolve])
        plan = plan_filter(filter_node)
        assert plan is not None

        surface = Surface.make(3, 3)
        surface.data[..., 0] = np.array([0.2, 0.5, 0.8], dtype=np.float32)
        surface.data[..., 3] = 1.0
        bounds = (0.0, 0.0, 3.0, 3.0)
        viewport = Viewport(
            width=3, height=3, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
        )
        return apply_filter(surface, plan, bounds, viewport)

    duplicate = run("duplicate")
    wrap = run("wrap")
    none = run("none")

    assert duplicate.data[1, 2, 0] == pytest.approx(0.8)
    assert wrap.data[1, 2, 0] == pytest.approx(0.2)
    assert none.data[1, 2, 0] == pytest.approx(0.0)
    assert duplicate.data[1, 2, 3] == pytest.approx(1.0)


def test_apply_filter_convolve_matrix_bias_preserves_transparent_alpha() -> None:
    convolve = FilterPrimitive(
        tag="feConvolveMatrix",
        attributes={
            "order": "1",
            "kernelMatrix": "1",
            "bias": "1",
            "preserveAlpha": "false",
        },
        styles={},
    )
    filter_node = _make_filter_node([convolve])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(2, 1)
    surface.data[0, 0, :] = np.array([0.0, 0.5, 0.0, 0.5], dtype=np.float32)
    surface.data[0, 1, :] = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    bounds = (0.0, 0.0, 2.0, 1.0)
    viewport = Viewport(
        width=2, height=1, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result = apply_filter(surface, plan, bounds, viewport)

    assert result.data[0, 0, 3] == pytest.approx(0.5)
    np.testing.assert_allclose(
        result.data[0, 0, :3],
        np.array([0.5, 0.5, 0.5], dtype=np.float32),
        atol=1e-6,
    )
    assert result.data[0, 1, 3] == pytest.approx(0.0)
    np.testing.assert_allclose(result.data[0, 1, :3], np.zeros(3), atol=1e-6)


def test_apply_filter_morphology_dilate() -> None:
    morphology = FilterPrimitive(
        tag="feMorphology", attributes={"operator": "dilate", "radius": "1"}, styles={}
    )
    filter_node = _make_filter_node([morphology])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(5, 5)
    surface.data[2, 2, 0] = 1.0
    surface.data[2, 2, 3] = 1.0

    bounds = (0.0, 0.0, 5.0, 5.0)
    viewport = Viewport(
        width=5, height=5, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result = apply_filter(surface, plan, bounds, viewport)
    active = result.data[..., 3] > 0.5
    assert np.count_nonzero(active) == 9


def test_plan_filter_component_transfer_gamma_triggers_fallback() -> None:
    component = FilterPrimitive(
        tag="feComponentTransfer",
        attributes={},
        styles={},
        children=(
            FilterPrimitive(
                tag="feFuncR", attributes={"type": "gamma", "amplitude": "1"}, styles={}
            ),
        ),
    )
    filter_node = _make_filter_node([component])

    assert plan_filter(filter_node) is None


def test_fe_tile_pass_through() -> None:
    tile = FilterPrimitive(tag="feTile", attributes={"in": "SourceGraphic"}, styles={})
    filter_node = _make_filter_node([tile])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(2, 2)
    surface.data[..., 0] = 0.2
    surface.data[..., 1] = 0.4
    surface.data[..., 2] = 0.6
    surface.data[..., 3] = 1.0

    bounds = (0.0, 0.0, 2.0, 2.0)
    viewport = Viewport(
        width=2, height=2, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result = apply_filter(surface, plan, bounds, viewport)
    np.testing.assert_allclose(result.data, surface.data, atol=1e-6)


def test_fe_image_embedded_data_uri() -> None:
    png_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
    image = FilterPrimitive(
        tag="feImage",
        attributes={"href": f"data:image/png;base64,{png_data}"},
        styles={},
    )
    filter_node = _make_filter_node([image])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(1, 1)
    bounds = (0.0, 0.0, 1.0, 1.0)
    viewport = Viewport(
        width=1, height=1, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result = apply_filter(surface, plan, bounds, viewport)
    pixel = result.data[0, 0]
    np.testing.assert_allclose(pixel[:3], np.array([1.0, 0.0, 0.0]), atol=1e-6)
    assert pixel[3] == pytest.approx(1.0)


def test_fe_image_local_file_with_source_path(tmp_path) -> None:
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
    )
    image_path = tmp_path / "pixel.png"
    image_path.write_bytes(png_data)

    image = FilterPrimitive(
        tag="feImage",
        attributes={"href": "pixel.png"},
        styles={},
    )
    filter_node = _make_filter_node([image])
    plan = plan_filter(
        filter_node, options={"source_path": str(tmp_path / "scene.svg")}
    )
    assert plan is not None

    surface = Surface.make(1, 1)
    bounds = (0.0, 0.0, 1.0, 1.0)
    viewport = Viewport(
        width=1, height=1, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result = apply_filter(surface, plan, bounds, viewport)
    pixel = result.data[0, 0]
    np.testing.assert_allclose(pixel[:3], np.array([1.0, 0.0, 0.0]), atol=1e-6)
    assert pixel[3] == pytest.approx(1.0)


def test_fe_image_local_file_missing_returns_no_plan(tmp_path) -> None:
    image = FilterPrimitive(
        tag="feImage",
        attributes={"href": "missing.png"},
        styles={},
    )
    filter_node = _make_filter_node([image])
    plan = plan_filter(
        filter_node, options={"source_path": str(tmp_path / "scene.svg")}
    )
    assert plan is None


def test_fe_image_local_file_outside_asset_root_returns_no_plan(tmp_path) -> None:
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
    )
    asset_root = tmp_path / "assets"
    asset_root.mkdir()
    outside = tmp_path / "pixel.png"
    outside.write_bytes(png_data)

    image = FilterPrimitive(
        tag="feImage",
        attributes={"href": str(outside)},
        styles={},
    )
    filter_node = _make_filter_node([image])

    plan = plan_filter(
        filter_node,
        options={
            "source_path": str(asset_root / "scene.svg"),
            "asset_root": str(asset_root),
        },
    )

    assert plan is None


def test_fe_image_file_uri_returns_no_plan(tmp_path) -> None:
    png_data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
    )
    image_path = tmp_path / "pixel.png"
    image_path.write_bytes(png_data)
    image = FilterPrimitive(
        tag="feImage",
        attributes={"href": image_path.as_uri()},
        styles={},
    )
    filter_node = _make_filter_node([image])

    plan = plan_filter(
        filter_node, options={"source_path": str(tmp_path / "scene.svg")}
    )

    assert plan is None


def test_filter_region_user_lengths_accept_svg_units() -> None:
    assert parse_user_length("1cm", 0.0, 100.0) == pytest.approx(37.7952755906)
    assert parse_user_length("25%", 0.0, 80.0) == pytest.approx(20.0)


def test_apply_filter_displacement_map_shifts_pixels() -> None:
    flood_map = FilterPrimitive(
        tag="feFlood",
        attributes={"result": "map", "flood-color": "#ff8080"},
        styles={},
    )
    displacement = FilterPrimitive(
        tag="feDisplacementMap",
        attributes={
            "in": "SourceGraphic",
            "in2": "map",
            "scale": "1",
            "xChannelSelector": "R",
            "yChannelSelector": "G",
        },
        styles={},
    )
    filter_node = _make_filter_node([flood_map, displacement])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(3, 3)
    surface.data[1, 1, 0] = 1.0
    surface.data[1, 1, 3] = 1.0

    bounds = (0.0, 0.0, 3.0, 3.0)
    viewport = Viewport(
        width=3, height=3, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result = apply_filter(surface, plan, bounds, viewport)

    assert result.data[1, 1, 0] == pytest.approx(0.0, abs=1e-6)
    assert result.data[1, 0, 0] == pytest.approx(1.0, abs=5e-3)


def test_apply_filter_turbulence_deterministic() -> None:
    turbulence = FilterPrimitive(
        tag="feTurbulence",
        attributes={
            "baseFrequency": "0.05 0.08",
            "numOctaves": "2",
            "seed": "7",
            "type": "fractalNoise",
        },
        styles={},
    )
    filter_node = _make_filter_node([turbulence])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(8, 6)
    bounds = (0.0, 0.0, 8.0, 6.0)
    viewport = Viewport(
        width=8, height=6, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result_a = apply_filter(surface, plan, bounds, viewport)
    result_b = apply_filter(surface, plan, bounds, viewport)
    assert np.allclose(result_a.data, result_b.data, atol=1e-6)
    assert np.var(result_a.data[..., 0]) > 0.0


def test_apply_filter_turbulence_stitch_tiles_edges_match() -> None:
    turbulence = FilterPrimitive(
        tag="feTurbulence",
        attributes={
            "baseFrequency": "0.08 0.12",
            "numOctaves": "3",
            "seed": "5",
            "stitchTiles": "stitch",
        },
        styles={},
    )
    filter_node = _make_filter_node([turbulence])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(24, 16)
    bounds = (0.0, 0.0, 24.0, 16.0)
    viewport = Viewport(
        width=24, height=16, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )
    result = apply_filter(surface, plan, bounds, viewport)

    np.testing.assert_allclose(result.data[:, 0, :], result.data[:, -1, :], atol=1e-3)
    np.testing.assert_allclose(result.data[0, :, :], result.data[-1, :, :], atol=1e-3)


def test_apply_filter_diffuse_lighting_basic() -> None:
    diffuse = FilterPrimitive(
        tag="feDiffuseLighting",
        attributes={
            "surfaceScale": "2",
            "diffuseConstant": "1.2",
            "result": "lit",
        },
        styles={"lighting-color": "#ffcc66"},
        children=(
            FilterPrimitive(
                tag="feDistantLight",
                attributes={"azimuth": "45", "elevation": "60"},
                styles={},
            ),
        ),
    )
    filter_node = _make_filter_node([diffuse])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(5, 5)
    surface.data[..., 3] = np.linspace(0.0, 1.0, 5, dtype=np.float32)[None, :]
    bounds = (0.0, 0.0, 5.0, 5.0)
    viewport = Viewport(
        width=5, height=5, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result = apply_filter(surface, plan, bounds, viewport)
    assert np.any(result.data[..., 0] > 0.0)
    assert result.data[..., 3].max() <= 1.0


def test_apply_filter_specular_lighting_basic() -> None:
    specular = FilterPrimitive(
        tag="feSpecularLighting",
        attributes={
            "surfaceScale": "3",
            "specularConstant": "1.0",
            "specularExponent": "5",
        },
        styles={"lighting-color": "#66ccff"},
        children=(
            FilterPrimitive(
                tag="feSpotLight",
                attributes={
                    "x": "2.5",
                    "y": "2.5",
                    "z": "5",
                    "pointsAtX": "2.5",
                    "pointsAtY": "2.5",
                    "pointsAtZ": "0",
                    "limitingConeAngle": "45",
                    "specularExponent": "2",
                },
                styles={},
            ),
        ),
    )
    filter_node = _make_filter_node([specular])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(5, 5)
    yy, xx = np.meshgrid(
        np.linspace(0.0, 1.0, 5, dtype=np.float32),
        np.linspace(0.0, 1.0, 5, dtype=np.float32),
    )
    surface.data[..., 3] = np.clip(xx * yy * 2.0, 0.0, 1.0)

    bounds = (0.0, 0.0, 5.0, 5.0)
    viewport = Viewport(
        width=5, height=5, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0
    )

    result = apply_filter(surface, plan, bounds, viewport)
    assert np.any(result.data[..., 0] > 0.0)
    assert 0.0 <= result.data[..., 3].max() <= 1.0


def test_light_direction_accepts_calc_metadata_values() -> None:
    units = SimpleNamespace(scale_x=1.0, scale_y=1.0)
    height_map = np.zeros((1, 1), dtype=np.float32)

    direction, weight = light_direction(
        {
            "type": "point",
            "x": "calc(0.25 + 0.25)",
            "y": "calc(0.25 + 0.25)",
            "z": "calc(2 + 3)",
        },
        1,
        1,
        units,
        height_map,
    )

    np.testing.assert_allclose(direction[0, 0], np.array([0.0, 0.0, 1.0]), atol=1e-6)
    assert weight[0, 0] == pytest.approx(1.0)
