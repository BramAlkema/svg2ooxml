from __future__ import annotations

import logging

from lxml import etree

from svg2ooxml.core.traversal import clipping
from svg2ooxml.core.traversal.geometry_utils import is_axis_aligned
from svg2ooxml.ir.geometry import LineSegment, Point, Rect
from svg2ooxml.ir.scene import ClipStrategy
from svg2ooxml.legacy.clipmask.types import ClipDefinition, MaskInfo
from svg2ooxml.common.geometry import Matrix2D


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
