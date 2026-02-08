"""Tests for the structured mask service."""

from __future__ import annotations

from svg2ooxml.ir.geometry import LineSegment, Point, Rect
from svg2ooxml.ir.scene import MaskDefinition, MaskMode, MaskRef
from svg2ooxml.services.mask_service import StructuredMaskService


def _simple_mask() -> MaskRef:
    definition = MaskDefinition(
        mask_id="mask1",
        bounding_box=Rect(0, 0, 5, 5),
        segments=(
            LineSegment(Point(0, 0), Point(5, 0)),
            LineSegment(Point(5, 0), Point(5, 5)),
            LineSegment(Point(5, 5), Point(0, 5)),
            LineSegment(Point(0, 5), Point(0, 0)),
        ),
    )
    return MaskRef(mask_id="mask1", definition=definition)


def test_mask_service_returns_geometry() -> None:
    service = StructuredMaskService()
    result = service.compute(_simple_mask())

    assert result is not None
    assert result.strategy == "native"
    assert result.geometry is not None
    assert result.geometry.geometry.xml.startswith("<a:custGeom>")
    assert result.metadata["classification"] == "vector"
    assert result.metadata["strategy"] == "native"
    assert result.metadata["fallback_order"][:2] == ("native", "mimic")


def test_mask_service_respects_policy() -> None:
    service = StructuredMaskService()
    result = service.compute(
        _simple_mask(),
        policy_options={"allow_vector_mask": False, "fallback_order": ("emf", "raster")},
    )

    assert result is not None
    assert result.strategy == "policy_emf"
    assert result.geometry is not None
    assert result.metadata["strategy"] == "policy_emf"
    assert result.metadata["fallback_order"] == ("emf", "raster")
    assert result.metadata.get("requires_emf") is True


def test_mask_service_detects_raster_content() -> None:
    service = StructuredMaskService()
    definition = MaskDefinition(
        mask_id="mask-raster",
        bounding_box=Rect(0, 0, 5, 5),
        segments=(
            LineSegment(Point(0, 0), Point(5, 0)),
            LineSegment(Point(5, 0), Point(5, 5)),
        ),
        content_xml=("<image href='texture.png' width='10' height='10' />",),
    )
    result = service.compute(MaskRef(mask_id="mask-raster", definition=definition))

    assert result is not None
    assert result.strategy == "raster"
    assert result.geometry is None
    assert result.metadata["classification"] in {"raster", "mixed"}
    assert result.metadata.get("requires_raster") is True
    assert "image" in result.metadata.get("raster_features", [])


def test_mask_service_flags_alpha_mode() -> None:
    service = StructuredMaskService()
    definition = MaskDefinition(
        mask_id="mask-alpha",
        bounding_box=Rect(0, 0, 4, 4),
        segments=(
            LineSegment(Point(0, 0), Point(4, 0)),
            LineSegment(Point(4, 0), Point(4, 4)),
        ),
        mode=MaskMode.ALPHA,
    )
    result = service.compute(MaskRef(mask_id="mask-alpha", definition=definition))

    assert result is not None
    assert result.strategy == "unsupported"
    assert result.metadata["classification"] == "unsupported"
    assert "alpha_mode" in result.metadata.get("unsupported_reasons", [])


def test_mask_service_policy_prefers_emf_order() -> None:
    service = StructuredMaskService()
    result = service.compute(
        _simple_mask(),
        policy_options={"fallback_order": ("emf", "native", "raster")},
    )

    assert result is not None
    assert result.strategy == "emf"
    assert result.metadata["strategy"] == "emf"
    assert result.metadata.get("requires_emf") is True
    assert result.geometry is not None


def test_mask_service_emf_threshold_triggers_raster() -> None:
    service = StructuredMaskService()
    result = service.compute(
        _simple_mask(),
        policy_options={
            "allow_vector_mask": False,
            "fallback_order": ("emf", "raster"),
            "max_emf_segments": 1,
        },
    )

    assert result is not None
    assert result.strategy == "policy_raster"
    assert result.metadata["strategy"] == "policy_raster"
    assert result.metadata.get("requires_raster") is True
    assert any("EMF fallback skipped" in message for message in result.diagnostics)


def test_mask_service_can_select_mimic() -> None:
    service = StructuredMaskService()
    result = service.compute(
        _simple_mask(),
        policy_options={"fallback_order": ("mimic", "emf")},
    )

    assert result is not None
    assert result.strategy == "mimic"
    assert result.metadata["strategy"] == "mimic"
    assert result.metadata.get("mimic_supported") is True
    assert result.geometry is not None and result.geometry.geometry is not None


def test_mask_service_uniform_opacity_uses_alpha_shortcut() -> None:
    """Mask with opacity < 1.0 and vector content uses alpha shortcut."""
    service = StructuredMaskService()
    definition = MaskDefinition(
        mask_id="mask-opacity",
        bounding_box=Rect(0, 0, 5, 5),
        opacity=0.5,
        segments=(
            LineSegment(Point(0, 0), Point(5, 0)),
            LineSegment(Point(5, 0), Point(5, 5)),
            LineSegment(Point(5, 5), Point(0, 5)),
            LineSegment(Point(0, 5), Point(0, 0)),
        ),
    )
    result = service.compute(MaskRef(mask_id="mask-opacity", definition=definition))

    assert result is not None
    assert result.strategy == "alpha"
    assert result.metadata["classification"] == "uniform_opacity"
    assert result.metadata["alpha_value"] == 0.5
    assert result.geometry is None


def test_mask_service_full_opacity_stays_vector() -> None:
    """Mask with opacity=1.0 is NOT treated as uniform opacity shortcut."""
    service = StructuredMaskService()
    definition = MaskDefinition(
        mask_id="mask-full",
        bounding_box=Rect(0, 0, 5, 5),
        opacity=1.0,
        segments=(
            LineSegment(Point(0, 0), Point(5, 0)),
            LineSegment(Point(5, 0), Point(5, 5)),
        ),
    )
    result = service.compute(MaskRef(mask_id="mask-full", definition=definition))

    assert result is not None
    assert result.strategy == "native"
    assert result.metadata["classification"] == "vector"


def test_mask_service_opacity_with_raster_skips_shortcut() -> None:
    """Mask with opacity < 1.0 but raster content does NOT use alpha shortcut."""
    service = StructuredMaskService()
    definition = MaskDefinition(
        mask_id="mask-raster-opacity",
        bounding_box=Rect(0, 0, 5, 5),
        opacity=0.5,
        segments=(
            LineSegment(Point(0, 0), Point(5, 0)),
            LineSegment(Point(5, 0), Point(5, 5)),
        ),
        content_xml=("<image href='texture.png' width='10' height='10'/>",),
    )
    result = service.compute(MaskRef(mask_id="mask-raster-opacity", definition=definition))

    assert result is not None
    # Should fall back to raster, not alpha shortcut
    assert result.strategy != "alpha"
    assert result.metadata["classification"] in {"raster", "mixed"}
