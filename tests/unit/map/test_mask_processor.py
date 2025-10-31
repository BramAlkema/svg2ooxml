"""Tests for the mask processor policy integration."""

from __future__ import annotations

import pytest

from svg2ooxml.ir.geometry import LineSegment, Point, Rect
from svg2ooxml.ir.scene import MaskDefinition, MaskInstance, MaskRef, Path
from svg2ooxml.core.masks import MaskProcessingResult, MaskProcessor


def _make_path(mask: MaskRef | None = None) -> Path:
    segment = LineSegment(start=Point(0, 0), end=Point(10, 10))
    mask_instance = MaskInstance(mask=mask) if mask is not None else None
    return Path(
        segments=[segment],
        fill=None,
        stroke=None,
        clip=None,
        mask=mask,
        mask_instance=mask_instance,
        opacity=1.0,
    )


def test_process_without_mask_returns_no_fallback() -> None:
    processor = MaskProcessor()
    path = _make_path()

    result = processor.process(path)

    assert isinstance(result, MaskProcessingResult)
    assert result.requires_emf is False
    assert result.metadata == {}


def test_process_with_mask_records_metadata() -> None:
    mask_def = MaskDefinition(
        mask_id="mask1",
        opacity=0.5,
        bounding_box=Rect(0, 0, 5, 5),
        segments=(
            LineSegment(Point(0, 0), Point(5, 0)),
            LineSegment(Point(5, 0), Point(5, 5)),
            LineSegment(Point(5, 5), Point(0, 5)),
            LineSegment(Point(0, 5), Point(0, 0)),
        ),
    )
    mask_ref = MaskRef(
        mask_id="url(#mask1)",
        definition=mask_def,
        target_bounds=mask_def.bounding_box,
        target_opacity=mask_def.opacity,
    )
    processor = MaskProcessor()
    path = _make_path(mask_ref)

    result = processor.process(path)

    assert result.requires_emf is False
    assert result.metadata["mask_id"] == "url(#mask1)"
    assert result.metadata["definition_id"] == "mask1"
    assert result.metadata["mask_mode"] == "auto"
    assert result.metadata["target_bounds"] == mask_def.bounding_box
    assert result.metadata["classification"] == "vector"
    assert result.metadata["strategy"] == "native"
    assert result.metadata["element_type"] == "Path"
    assert result.metadata.get("requires_emf") is False
    assert result.xml_fragment.strip().startswith("<a:custGeom>")


def test_process_with_policy_attaches_summary() -> None:
    mask_def = MaskDefinition(
        mask_id="mask1",
        segments=(
            LineSegment(Point(0, 0), Point(5, 0)),
            LineSegment(Point(5, 0), Point(5, 5)),
            LineSegment(Point(5, 5), Point(0, 5)),
            LineSegment(Point(0, 5), Point(0, 0)),
        ),
    )
    mask_ref = MaskRef(mask_id="mask1", definition=mask_def)
    processor = MaskProcessor()
    path = _make_path(mask_ref)

    options = {
        "allow_vector_mask": True,
        "fallback_order": ("native", "emf", "raster"),
        "max_bitmap_area": 1024,
        "max_bitmap_side": 256,
    }

    result = processor.process(path, policy_options=options)

    policy_meta = result.metadata.get("policy", {}).get("mask")
    assert policy_meta is not None
    assert policy_meta["allow_vector_mask"] is True
    assert policy_meta["max_bitmap_area"] == 1024
    assert policy_meta["fallback_order"] == tuple(options["fallback_order"])
    assert result.requires_emf is False
    assert result.metadata["strategy"] == "native"


def test_policy_forces_emf_when_vector_disallowed() -> None:
    mask_def = MaskDefinition(
        mask_id="mask1",
        segments=(
            LineSegment(Point(0, 0), Point(5, 0)),
            LineSegment(Point(5, 0), Point(5, 5)),
            LineSegment(Point(5, 5), Point(0, 5)),
            LineSegment(Point(0, 5), Point(0, 0)),
        ),
    )
    mask_ref = MaskRef(mask_id="mask1", definition=mask_def)
    processor = MaskProcessor()
    path = _make_path(mask_ref)

    result = processor.process(
        path,
        policy_options={"allow_vector_mask": False, "fallback_order": ("emf", "raster")},
    )

    assert result.requires_emf is True
    assert result.metadata.get("requires_emf") is True
    assert result.metadata.get("strategy") == "policy_emf"
    assert result.metadata.get("fallback_order") == ("emf", "raster")


def test_process_with_raster_mask_marks_raster_fallback() -> None:
    mask_def = MaskDefinition(
        mask_id="mask-raster",
        bounding_box=Rect(0, 0, 5, 5),
        segments=(
            LineSegment(Point(0, 0), Point(5, 0)),
            LineSegment(Point(5, 0), Point(5, 5)),
        ),
        content_xml=("<image href='texture.png' width='10' height='10' />",),
    )
    mask_ref = MaskRef(mask_id="mask-raster", definition=mask_def)
    processor = MaskProcessor()
    path = _make_path(mask_ref)

    result = processor.process(path)

    assert result.requires_emf is True
    assert result.metadata.get("strategy") == "raster"
    assert result.metadata.get("requires_raster") is True
    assert "image" in result.metadata.get("raster_features", [])


def test_policy_emf_threshold_drops_to_raster() -> None:
    mask_def = MaskDefinition(
        mask_id="mask-threshold",
        bounding_box=Rect(0, 0, 5, 5),
        segments=(
            LineSegment(Point(0, 0), Point(5, 0)),
            LineSegment(Point(5, 0), Point(5, 5)),
            LineSegment(Point(5, 5), Point(0, 5)),
            LineSegment(Point(0, 5), Point(0, 0)),
        ),
    )
    mask_ref = MaskRef(mask_id="mask-threshold", definition=mask_def)
    processor = MaskProcessor()
    path = _make_path(mask_ref)

    result = processor.process(
        path,
        policy_options={
            "allow_vector_mask": False,
            "fallback_order": ("emf", "raster"),
            "max_emf_segments": 1,
        },
    )

    assert result.requires_emf is True
    assert result.metadata.get("strategy") == "policy_raster"
    assert result.metadata.get("requires_raster") is True
