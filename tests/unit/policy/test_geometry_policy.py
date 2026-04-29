"""Tests for geometry policy helpers."""

from __future__ import annotations

from svg2ooxml.ir.geometry import LineSegment, Point
from svg2ooxml.policy.constants import FALLBACK_BITMAP, FALLBACK_EMF, FALLBACK_NATIVE
from svg2ooxml.policy.geometry import apply_geometry_policy


def _build_segments(count: int) -> list[LineSegment]:
    segments: list[LineSegment] = []
    cursor = Point(0.0, 0.0)
    for index in range(count):
        next_point = Point(float(index + 1), 0.0)
        segments.append(LineSegment(cursor, next_point))
        cursor = next_point
    return segments


def test_apply_geometry_policy_no_policy_returns_native() -> None:
    segments = _build_segments(4)

    result_segments, metadata, mode = apply_geometry_policy(segments, None)

    assert result_segments == segments
    assert metadata == {}
    assert mode == FALLBACK_NATIVE


def test_apply_geometry_policy_force_bitmap() -> None:
    segments = _build_segments(2)

    _, metadata, mode = apply_geometry_policy(segments, {"force_bitmap": True})

    assert metadata["render_mode"] == FALLBACK_BITMAP
    assert mode == FALLBACK_BITMAP


def test_apply_geometry_policy_force_emf() -> None:
    segments = _build_segments(2)

    _, metadata, mode = apply_geometry_policy(segments, {"force_emf": True})

    assert metadata["render_mode"] == FALLBACK_EMF
    assert mode == FALLBACK_EMF


def test_apply_geometry_policy_simplifies_when_allowed() -> None:
    segments = _build_segments(20)

    simplified, metadata, mode = apply_geometry_policy(
        segments,
        {"max_segments": 4, "simplify_paths": True, "simplify_min_segments": 2},
    )

    # Collinear segments are merged by the simplification pass
    assert len(simplified) < len(segments)
    assert metadata["segments_before_simplify"] == 20
    assert metadata["simplified"] is True
    assert mode == "native"  # under max_segments after simplification


def test_apply_geometry_policy_marks_complexity_exceeded() -> None:
    segments = _build_segments(6)

    _, metadata, mode = apply_geometry_policy(
        segments,
        {
            "max_segments": 2,
            "max_complexity": 1.5,
        },
    )

    assert metadata["render_mode"] == FALLBACK_EMF
    assert "complexity_exceeded" in metadata.get("flags", [])
    assert mode == FALLBACK_EMF


def test_apply_geometry_policy_skips_emf_when_disallowed() -> None:
    segments = _build_segments(6)

    _, metadata, mode = apply_geometry_policy(
        segments,
        {
            "max_segments": 2,
            "max_complexity": 1.5,
            "allow_emf_fallback": False,
        },
    )

    assert metadata["render_mode"] == FALLBACK_NATIVE
    assert mode == FALLBACK_NATIVE


def test_apply_geometry_policy_ignores_invalid_numeric_policy_values() -> None:
    segments = _build_segments(4)

    _, metadata, mode = apply_geometry_policy(
        segments,
        {
            "max_segments": "bad",
            "max_complexity": "nan",
            "detect_preset_shapes": False,
            "simplify_paths": True,
            "simplify_min_segments": "bad",
            "simplify_epsilon_px": "bad",
            "bezier_flatness_px": "inf",
            "collinear_angle_deg": "bad",
            "rdp_tolerance_px": "bad",
            "curve_fit_tolerance_px": "bad",
            "curve_fit_min_points": "bad",
        },
    )

    assert metadata["render_mode"] == FALLBACK_NATIVE
    assert mode == FALLBACK_NATIVE
