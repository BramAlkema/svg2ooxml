from __future__ import annotations

import logging

from lxml import etree

from svg2ooxml.clipmask.types import ClipDefinition, MaskInfo
from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.core.traversal import clipping
from svg2ooxml.core.traversal.geometry_utils import is_axis_aligned
from svg2ooxml.ir.geometry import LineSegment, Point, Rect
from svg2ooxml.ir.scene import ClipStrategy


class DummyServices:
    drawingml_path_generator = None


def test_resolve_clip_ref_without_clip_returns_none() -> None:
    element = etree.fromstring("<rect xmlns='http://www.w3.org/2000/svg' width='10' height='10' />")

    result = clipping.resolve_clip_ref(
        element,
        clip_definitions={},
        services=DummyServices(),
        logger=logging.getLogger(__name__),
        tolerance=1e-6,
        is_axis_aligned=is_axis_aligned,
    )

    assert result is None


def test_resolve_clip_ref_returns_clipref_with_native_geometry() -> None:
    primitive = {
        "type": "rect",
        "transform": (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        "rx": 0,
        "ry": 0,
    }
    definition = ClipDefinition(
        clip_id="clip1",
        segments=(
            LineSegment(Point(0, 0), Point(10, 0)),
            LineSegment(Point(10, 0), Point(10, 10)),
            LineSegment(Point(10, 10), Point(0, 10)),
            LineSegment(Point(0, 10), Point(0, 0)),
        ),
        bounding_box=Rect(x=0, y=0, width=10, height=10),
        clip_rule="nonzero",
        transform=Matrix2D.identity(),
        primitives=(primitive,),
    )

    element = etree.fromstring(
        """
        <rect xmlns='http://www.w3.org/2000/svg'
              width='10' height='10' clip-path='url(#clip1)'/>
        """
    )

    result = clipping.resolve_clip_ref(
        element,
        clip_definitions={"clip1": definition},
        services=DummyServices(),
        logger=logging.getLogger(__name__),
        tolerance=1e-6,
        is_axis_aligned=is_axis_aligned,
    )

    assert result is not None
    assert result.clip_id == "clip1"
    assert result.strategy == ClipStrategy.NATIVE
    assert result.custom_geometry_xml is not None


def test_resolve_clip_ref_transforms_definition_to_use_space() -> None:
    primitive = {
        "type": "rect",
        "transform": (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        "rx": 0,
        "ry": 0,
    }
    definition = ClipDefinition(
        clip_id="clip1",
        segments=(
            LineSegment(Point(0, 0), Point(10, 0)),
            LineSegment(Point(10, 0), Point(10, 10)),
            LineSegment(Point(10, 10), Point(0, 10)),
            LineSegment(Point(0, 10), Point(0, 0)),
        ),
        bounding_box=Rect(x=0, y=0, width=10, height=10),
        clip_rule="nonzero",
        transform=Matrix2D.identity(),
        primitives=(primitive,),
    )
    element = etree.fromstring(
        """
        <rect xmlns='http://www.w3.org/2000/svg'
              width='10' height='10' clip-path='url(#clip1)'/>
        """
    )

    result = clipping.resolve_clip_ref(
        element,
        clip_definitions={"clip1": definition},
        services=DummyServices(),
        logger=logging.getLogger(__name__),
        tolerance=1e-6,
        is_axis_aligned=is_axis_aligned,
        use_transform=Matrix2D.translate(20, 70),
    )

    assert result is not None
    assert result.bounding_box == Rect(20, 70, 10, 10)
    assert result.path_segments is not None
    assert result.path_segments[0].start == Point(20, 70)
    assert result.path_segments[0].end == Point(30, 70)
    assert result.primitives[0]["transform"] == (1.0, 0.0, 0.0, 1.0, 20.0, 70.0)


def test_resolve_clip_ref_accepts_length_units_on_round_rect_radii() -> None:
    primitive = {
        "type": "rect",
        "transform": (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
        "rx": "2px",
        "ry": "3px",
    }
    definition = ClipDefinition(
        clip_id="clip2",
        segments=(
            LineSegment(Point(0, 0), Point(10, 0)),
            LineSegment(Point(10, 0), Point(10, 10)),
            LineSegment(Point(10, 10), Point(0, 10)),
            LineSegment(Point(0, 10), Point(0, 0)),
        ),
        bounding_box=Rect(x=0, y=0, width=10, height=10),
        clip_rule="nonzero",
        transform=Matrix2D.identity(),
        primitives=(primitive,),
    )
    element = etree.fromstring(
        """
        <rect xmlns='http://www.w3.org/2000/svg'
              width='10' height='10' clip-path='url(#clip2)'/>
        """
    )

    result = clipping.resolve_clip_ref(
        element,
        clip_definitions={"clip2": definition},
        services=DummyServices(),
        logger=logging.getLogger(__name__),
        tolerance=1e-6,
        is_axis_aligned=is_axis_aligned,
    )

    assert result is not None
    assert result.custom_geometry_xml is not None


def test_resolve_mask_ref_returns_instance() -> None:
    mask_info = MaskInfo(
        mask_id="mask1",
        mask_type="alpha",
        mode="alpha",
        mask_units="objectBoundingBox",
        mask_content_units="userSpaceOnUse",
        region=Rect(x=0, y=0, width=10, height=10),
        opacity=0.5,
        transform=Matrix2D.identity(),
        children=(),
        bounding_box=Rect(x=0, y=0, width=10, height=10),
    )

    element = etree.fromstring(
        """
        <rect xmlns='http://www.w3.org/2000/svg'
              width='10' height='10' mask='url(#mask1)'/>
        """
    )

    mask_ref, mask_instance = clipping.resolve_mask_ref(
        element,
        mask_info={"mask1": mask_info},
    )

    assert mask_ref is not None
    assert mask_ref.mask_id == "mask1"
    assert mask_instance is not None
    assert mask_instance.mask is mask_ref
