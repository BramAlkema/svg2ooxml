"""Tests for mapper scaffolding helpers."""

from __future__ import annotations

import pytest

from dataclasses import dataclass

from svg2ooxml.core.traversal.clip_geometry import (
    ClipComputeResult,
    ClipCustGeom,
    ClipFallback,
    compute_clip_geometry,
)
from svg2ooxml.core.pipeline.mappers import (
    Mapper,
    MapperError,
    MapperResult,
    OutputFormat,
    clip_result_to_xml,
    validate_mapper_result,
)
from svg2ooxml.ir.geometry import LineSegment, Point
from svg2ooxml.ir.scene import ClipRef, MaskDefinition, MaskRef
from svg2ooxml.ir.geometry import Rect


class DummyMapper(Mapper):
    def can_map(self, element) -> bool:
        return isinstance(element, dict)

    def map(self, element) -> MapperResult:
        if not self.can_map(element):
            raise MapperError("unsupported", element)
        result = MapperResult(
            element=element,
            output_format=OutputFormat.NATIVE_DML,
            xml_content="<a/>",
            metadata={"value": element.get("value")},
        )
        self._record_mapping(result)
        return result


def test_mapper_result_validation_passes() -> None:
    result = MapperResult(
        element={"id": "el"},
        output_format=OutputFormat.NATIVE_DML,
        xml_content="<shape/>",
        metadata={},
    )
    assert validate_mapper_result(result)


def test_mapper_statistics_track_mappings() -> None:
    mapper = DummyMapper(policy=None)
    mapper.map({"value": 1})
    stats = mapper.get_statistics()
    assert stats["total_mapped"] == 1
    assert stats["native_count"] == 1
    mapper.reset_statistics()
    stats = mapper.get_statistics()
    assert stats["total_mapped"] == 0


def test_clip_render_handles_missing_result() -> None:
    xml, metadata, media = clip_result_to_xml(None, clip_ref=None)
    assert "Clip unavailable" in xml
    assert metadata["strategy"] == "unavailable"
    assert media is None


def test_clip_render_infers_xml_and_media() -> None:
    custgeom = ClipCustGeom(path_xml="<path/>")
    @dataclass
    class _Media:
        content_type: str
        rel_id: str | None
        part_name: str | None
        bbox_emu: tuple[int, int, int, int]
        data: bytes | None = None
        description: str | None = None

    media_meta = _Media(
        content_type="image/png",
        rel_id="rId1",
        part_name="/ppt/media/image1.png",
        bbox_emu=(0, 0, 100, 200),
        data=b"00",
        description="clip mask",
    )
    result = ClipComputeResult(
        strategy=ClipFallback.NONE,
        custgeom=custgeom,
        media=media_meta,
        metadata={"hint": "value"},
    )
    clip_xml, metadata, media_files = clip_result_to_xml(result)
    assert clip_xml == "<path/>"
    assert metadata["strategy"] == "native"
    assert media_files and media_files[0]["type"] == "image"


def test_compute_clip_geometry_generates_drawingml() -> None:
    segments = [
        LineSegment(Point(0, 0), Point(20, 0)),
        LineSegment(Point(20, 0), Point(20, 10)),
        LineSegment(Point(20, 10), Point(0, 10)),
        LineSegment(Point(0, 10), Point(0, 0)),
    ]
    clip_ref = ClipRef(clip_id="clip-rect", path_segments=tuple(segments))

    result = compute_clip_geometry(clip_ref)
    assert result is not None
    assert result.strategy == ClipFallback.NONE
    assert result.custgeom is not None
    assert "custGeom" in result.custgeom.path_xml

    xml, metadata, media = clip_result_to_xml(result, clip_ref)
    assert "moveTo" in xml
    assert metadata["strategy"] == "native"
    assert metadata["segment_count"] == len(segments)
    assert media is None


def test_compute_clip_geometry_from_mask_primitives() -> None:
    primitive = {
        "type": "rect",
        "x": 0.0,
        "y": 0.0,
        "width": 15.0,
        "height": 5.0,
        "transform": (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
    }
    mask_def = MaskDefinition(
        mask_id="mask-1",
        mask_type=None,
        mask_units=None,
        mask_content_units=None,
        opacity=None,
        bounding_box=Rect(0.0, 0.0, 15.0, 5.0),
        primitives=(primitive,),
    )
    mask_ref = MaskRef(mask_id="mask-1", definition=mask_def)

    result = compute_clip_geometry(mask_ref)
    assert result is not None
    assert result.custgeom is not None
    assert "custGeom" in result.custgeom.path_xml
    assert result.custgeom.bbox_emu is not None


def test_compute_clip_geometry_from_mask_path() -> None:
    primitive = {
        "type": "path",
        "d": "M0 0 L10 0 L10 5 Z",
        "transform": (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
    }
    mask_def = MaskDefinition(
        mask_id="mask-path",
        mask_type=None,
        mask_units=None,
        mask_content_units=None,
        opacity=None,
        bounding_box=Rect(0.0, 0.0, 10.0, 5.0),
        primitives=(primitive,),
    )
    mask_ref = MaskRef(mask_id="mask-path", definition=mask_def)

    result = compute_clip_geometry(mask_ref)
    assert result is not None
    assert result.custgeom is not None
    assert "custGeom" in result.custgeom.path_xml
