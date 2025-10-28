"""Core-level tests for the mask processor."""

from __future__ import annotations

import pytest

from svg2ooxml.core.masks import MaskProcessingResult, MaskProcessor
from svg2ooxml.ir.geometry import LineSegment, Point, Rect
from svg2ooxml.ir.scene import MaskDefinition, MaskInstance, MaskRef, Path


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
    assert result.metadata.get("mask_id") == "url(#mask1)"
    assert result.metadata.get("definition_id") == "mask1"
    assert result.metadata.get("target_bounds") == mask_def.bounding_box


def test_process_returns_emf_when_service_falls_back(monkeypatch) -> None:
    processor = MaskProcessor()
    monkeypatch.setattr(processor, "_mask_service", type("Svc", (), {"compute": lambda self, *a, **k: None})())
    path = _make_path(MaskRef(mask_id="mask2"))

    result = processor.process(path)

    assert result.requires_emf is True
