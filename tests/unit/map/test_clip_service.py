"""Tests for the structured clip service."""

from __future__ import annotations

from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.scene import ClipRef
from svg2ooxml.map.mapper.clip_geometry import ClipComputeResult, ClipFallback
from svg2ooxml.services.clip_service import ClipAnalysis, StructuredClipService


def _simple_clip_ref() -> ClipRef:
    return ClipRef(
        clip_id="clip-1",
        path_segments=(),
        primitives=(
            {
                "type": "rect",
                "x": 0.0,
                "y": 0.0,
                "width": 10.0,
                "height": 5.0,
                "transform": (1.0, 0.0, 0.0, 1.0, 0.0, 0.0),
            },
        ),
    )


def test_structured_clip_service_produces_geometry() -> None:
    service = StructuredClipService()
    clip_ref = _simple_clip_ref()

    result = service.compute(clip_ref)

    assert isinstance(result, ClipComputeResult)
    assert result.strategy == ClipFallback.NONE
    assert result.custgeom is not None
    assert result.custgeom.path_xml is not None


def test_structured_clip_service_falls_back_to_bbox() -> None:
    service = StructuredClipService()
    clip_ref = ClipRef(clip_id="clip-bbox", path_segments=None, bounding_box=Rect(0, 0, 4, 6))

    result = service.compute(clip_ref)
    assert result is not None
    assert result.used_bbox_rect is True
    assert result.custgeom is not None
    assert result.custgeom.bbox_emu == (0, 0, 38100, 57150)


def test_structured_clip_service_respects_emf_requirement() -> None:
    service = StructuredClipService()
    clip_ref = _simple_clip_ref()
    analysis = ClipAnalysis(requires_emf=True)

    result = service.compute(clip_ref, analysis)
    assert result is not None
    assert result.strategy == ClipFallback.EMF_SHAPE
