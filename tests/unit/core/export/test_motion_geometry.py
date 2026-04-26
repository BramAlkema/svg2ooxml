from __future__ import annotations

from svg2ooxml.core.export.element_translation import (
    _translate_element_to_center_target,
    _translate_element_to_motion_start,
)
from svg2ooxml.core.export.motion_path_sampling import (
    _parse_sampled_motion_points,
    _sample_polyline_at_fraction,
    _sample_polyline_at_fractions,
)
from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.scene import Group
from svg2ooxml.ir.shapes import Rectangle


def test_translate_element_to_center_target_moves_rectangle_by_center_delta() -> None:
    rect = Rectangle(
        bounds=Rect(0.0, 0.0, 10.0, 20.0),
        metadata={"element_ids": ["shape"]},
    )

    moved = _translate_element_to_center_target(rect, {"shape": (15.0, 20.0)})

    assert moved.bounds == Rect(10.0, 10.0, 10.0, 20.0)


def test_translate_element_to_center_target_moves_group_children() -> None:
    group = Group(
        children=[
            Rectangle(
                bounds=Rect(0.0, 0.0, 10.0, 10.0),
                metadata={"element_ids": ["child"]},
            )
        ],
        metadata={"element_ids": ["group"]},
    )

    moved = _translate_element_to_center_target(group, {"group": (15.0, 15.0)})

    assert moved.children[0].bounds == Rect(10.0, 10.0, 10.0, 10.0)


def test_translate_element_to_motion_start_moves_rectangle_by_top_left_delta() -> None:
    rect = Rectangle(
        bounds=Rect(10.0, 20.0, 30.0, 40.0),
        metadata={"element_ids": ["shape"]},
    )

    moved = _translate_element_to_motion_start(rect, {"shape": (25.0, 45.0)})

    assert moved.bounds == Rect(25.0, 45.0, 30.0, 40.0)


def test_sample_polyline_at_fractions_matches_single_fraction_sampler() -> None:
    points = [(0.0, 0.0), (10.0, 0.0), (10.0, 20.0)]
    fractions = [0.0, 0.25, 0.5, 1.0]
    unsorted_fractions = [0.75, 0.25]

    batched = _sample_polyline_at_fractions(points, fractions)
    unsorted_batched = _sample_polyline_at_fractions(points, unsorted_fractions)

    assert batched == [
        _sample_polyline_at_fraction(points, fraction)
        for fraction in fractions
    ]
    assert unsorted_batched == [
        _sample_polyline_at_fraction(points, fraction)
        for fraction in unsorted_fractions
    ]


def test_parse_sampled_motion_points_accepts_powerpoint_end_marker() -> None:
    assert _parse_sampled_motion_points("M 0 0 L 10 0 E") == [
        (0.0, 0.0),
        (10.0, 0.0),
    ]
