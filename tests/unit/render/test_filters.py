from __future__ import annotations

import base64

import numpy as np
import pytest

from svg2ooxml.core.resvg.parser.presentation import Presentation
from svg2ooxml.core.resvg.usvg_tree import FilterNode, FilterPrimitive
from svg2ooxml.render.filters import apply_filter, plan_filter
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


def test_plan_filter_rejects_unsupported_primitive() -> None:
    primitive = FilterPrimitive(
        tag="feDropShadow",
        attributes={"result": "shadow"},
        styles={},
    )
    filter_node = _make_filter_node([primitive])

    plan = plan_filter(filter_node)

    assert plan is None


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
    viewport = Viewport(width=4, height=4, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0)

    result = apply_filter(surface, plan, bounds, viewport)

    pixel = result.data[0, 0]
    np.testing.assert_allclose(pixel[:3], np.array([1.0, 0.0, 1.0]), rtol=1e-4, atol=1e-4)
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
            FilterPrimitive(tag="feMergeNode", attributes={"in": "SourceGraphic"}, styles={}),
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
    viewport = Viewport(width=2, height=2, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0)

    result = apply_filter(surface, plan, bounds, viewport)

    pixel = result.data[0, 0]
    np.testing.assert_allclose(pixel[:3], np.array([0.5, 0.5, 0.0]), rtol=1e-4, atol=1e-4)
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
    viewport = Viewport(width=2, height=2, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0)

    result = apply_filter(surface, plan, bounds, viewport)

    assert result.data[0, 0, 1] == pytest.approx(0.5)
    assert result.data[0, 0, 3] == pytest.approx(0.5)


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

    surface = Surface.make(2, 2)
    bounds = (0.0, 0.0, 2.0, 2.0)
    viewport = Viewport(width=2, height=2, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0)

    result = apply_filter(surface, plan, bounds, viewport)
    pixel = result.data[0, 0]
    np.testing.assert_allclose(pixel[:3], np.array([0.25, 0.0, 0.75], dtype=np.float32), atol=1e-6)
    assert pixel[3] == pytest.approx(1.0)


def test_apply_filter_component_transfer_linear_and_table() -> None:
    component = FilterPrimitive(
        tag="feComponentTransfer",
        attributes={"result": "adjusted"},
        styles={},
        children=(
            FilterPrimitive(tag="feFuncR", attributes={"type": "linear", "slope": "0.5"}, styles={}),
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
    viewport = Viewport(width=1, height=1, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0)

    result = apply_filter(surface, plan, bounds, viewport)
    pixel = result.data[0, 0]
    np.testing.assert_allclose(pixel[:3], np.array([0.3, 0.4, 0.8], dtype=np.float32), atol=1e-3)
    assert pixel[3] == pytest.approx(1.0)


def test_apply_filter_morphology_dilate() -> None:
    morphology = FilterPrimitive(tag="feMorphology", attributes={"operator": "dilate", "radius": "1"}, styles={})
    filter_node = _make_filter_node([morphology])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(5, 5)
    surface.data[2, 2, 0] = 1.0
    surface.data[2, 2, 3] = 1.0

    bounds = (0.0, 0.0, 5.0, 5.0)
    viewport = Viewport(width=5, height=5, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0)

    result = apply_filter(surface, plan, bounds, viewport)
    active = result.data[..., 3] > 0.5
    assert np.count_nonzero(active) == 9


def test_plan_filter_component_transfer_gamma_triggers_fallback() -> None:
    component = FilterPrimitive(
        tag="feComponentTransfer",
        attributes={},
        styles={},
        children=(
            FilterPrimitive(tag="feFuncR", attributes={"type": "gamma", "amplitude": "1"}, styles={}),
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
    viewport = Viewport(width=2, height=2, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0)

    result = apply_filter(surface, plan, bounds, viewport)
    np.testing.assert_allclose(result.data, surface.data, atol=1e-6)


def test_fe_image_embedded_data_uri() -> None:
    png_data = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
    )
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
    viewport = Viewport(width=1, height=1, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0)

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
    plan = plan_filter(filter_node, options={"source_path": str(tmp_path / "scene.svg")})
    assert plan is not None

    surface = Surface.make(1, 1)
    bounds = (0.0, 0.0, 1.0, 1.0)
    viewport = Viewport(width=1, height=1, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0)

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
    plan = plan_filter(filter_node, options={"source_path": str(tmp_path / "scene.svg")})
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
        options={"source_path": str(asset_root / "scene.svg"), "asset_root": str(asset_root)},
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

    plan = plan_filter(filter_node, options={"source_path": str(tmp_path / "scene.svg")})

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
    viewport = Viewport(width=3, height=3, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0)

    result = apply_filter(surface, plan, bounds, viewport)

    assert result.data[1, 1, 0] == pytest.approx(0.0, abs=1e-6)
    assert result.data[1, 0, 0] == pytest.approx(1.0, abs=5e-3)


def test_apply_filter_turbulence_deterministic() -> None:
    turbulence = FilterPrimitive(
        tag="feTurbulence",
        attributes={"baseFrequency": "0.05 0.08", "numOctaves": "2", "seed": "7", "type": "fractalNoise"},
        styles={},
    )
    filter_node = _make_filter_node([turbulence])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(8, 6)
    bounds = (0.0, 0.0, 8.0, 6.0)
    viewport = Viewport(width=8, height=6, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0)

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
    viewport = Viewport(width=24, height=16, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0)
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
            FilterPrimitive(tag="feDistantLight", attributes={"azimuth": "45", "elevation": "60"}, styles={}),
        ),
    )
    filter_node = _make_filter_node([diffuse])
    plan = plan_filter(filter_node)
    assert plan is not None

    surface = Surface.make(5, 5)
    surface.data[..., 3] = np.linspace(0.0, 1.0, 5, dtype=np.float32)[None, :]
    bounds = (0.0, 0.0, 5.0, 5.0)
    viewport = Viewport(width=5, height=5, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0)

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
    yy, xx = np.meshgrid(np.linspace(0.0, 1.0, 5, dtype=np.float32), np.linspace(0.0, 1.0, 5, dtype=np.float32))
    surface.data[..., 3] = np.clip(xx * yy * 2.0, 0.0, 1.0)

    bounds = (0.0, 0.0, 5.0, 5.0)
    viewport = Viewport(width=5, height=5, min_x=0.0, min_y=0.0, scale_x=1.0, scale_y=1.0)

    result = apply_filter(surface, plan, bounds, viewport)
    assert np.any(result.data[..., 0] > 0.0)
    assert 0.0 <= result.data[..., 3].max() <= 1.0
