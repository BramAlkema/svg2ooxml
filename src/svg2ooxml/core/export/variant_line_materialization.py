"""Scene rewriting for animated simple line paths."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace as _replace
from typing import Any

from svg2ooxml.core.export.animation_predicates import (
    _is_simple_line_endpoint_animation,
)
from svg2ooxml.core.export.scene_index import _scene_element_ids
from svg2ooxml.core.ir.converter import IRScene
from svg2ooxml.ir.animation import AnimationDefinition
from svg2ooxml.ir.geometry import LineSegment
from svg2ooxml.ir.scene import Group
from svg2ooxml.ir.scene import Path as IRPath
from svg2ooxml.ir.shapes import Line


def _materialize_simple_line_paths(
    scene: IRScene,
    animations: Sequence[AnimationDefinition],
) -> None:
    """Convert simple animated single-segment paths back into line IR."""

    endpoint_target_ids = {
        animation.element_id
        for animation in animations
        if _is_simple_line_endpoint_animation(animation)
        and isinstance(animation.element_id, str)
    }
    if not endpoint_target_ids:
        return

    scene.elements = [
        _rewrite_line_path(element, endpoint_target_ids)
        for element in scene.elements
    ]


def _rewrite_line_path(element: Any, endpoint_target_ids: set[str]):
    if isinstance(element, Group):
        return _replace(
            element,
            children=[
                _rewrite_line_path(child, endpoint_target_ids)
                for child in element.children
            ],
        )
    if not isinstance(element, IRPath):
        return element
    if element.fill is not None or element.clip or element.mask or element.mask_instance:
        return element

    line_segments = [
        segment for segment in element.segments if isinstance(segment, LineSegment)
    ]
    if len(line_segments) != 1 or len(line_segments) != len(element.segments):
        return element
    if not any(
        element_id in endpoint_target_ids
        for element_id in _scene_element_ids(element)
    ):
        return element

    segment = line_segments[0]
    metadata = getattr(element, "metadata", None)
    return Line(
        start=segment.start,
        end=segment.end,
        stroke=element.stroke,
        opacity=element.opacity,
        effects=list(getattr(element, "effects", [])),
        metadata=dict(metadata) if isinstance(metadata, dict) else {},
    )


__all__ = ["_materialize_simple_line_paths"]
