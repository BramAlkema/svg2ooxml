from __future__ import annotations

from svg2ooxml.drawingml.markers import marker_end_elements


def test_marker_end_elements_infers_native_type_and_size() -> None:
    head, tail = marker_end_elements({"end": "arrow-large", "start": "dot-small"})

    assert head is not None
    assert head.get("type") == "arrow"
    assert head.get("w") == "lg"
    assert head.get("len") == "lg"

    assert tail is not None
    assert tail.get("type") == "oval"
    assert tail.get("w") == "sm"
    assert tail.get("len") == "sm"


def test_marker_end_elements_defaults_unknown_to_triangle_medium() -> None:
    head, tail = marker_end_elements({"end": "custom-end", "start": "custom-start"})

    assert head is not None
    assert head.get("type") == "triangle"
    assert head.get("w") == "med"
    assert head.get("len") == "med"

    assert tail is not None
    assert tail.get("type") == "triangle"
    assert tail.get("w") == "med"
    assert tail.get("len") == "med"


def test_marker_end_elements_prefers_geometry_profile_over_hint() -> None:
    head, tail = marker_end_elements(
        {"end": "arrow-large", "start": "dot-small"},
        marker_profiles={
            "end": {"type": "diamond", "size": "sm", "source": "geometry"},
            "start": {"type": "oval", "size": "lg", "source": "geometry"},
        },
    )

    assert head is not None
    assert head.get("type") == "diamond"
    assert head.get("w") == "sm"
    assert head.get("len") == "sm"

    assert tail is not None
    assert tail.get("type") == "oval"
    assert tail.get("w") == "lg"
    assert tail.get("len") == "lg"
