"""Scene element translation helpers for animation preprocessing."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _element_ids_for_translation(element: Any) -> list[str]:
    metadata = getattr(element, "metadata", None)
    raw_ids = metadata.get("element_ids", []) if isinstance(metadata, dict) else []
    return [element_id for element_id in raw_ids if isinstance(element_id, str)]


def _has_translation_delta(dx: float, dy: float) -> bool:
    return abs(dx) > 1e-9 or abs(dy) > 1e-9


def _center_target_delta(
    element: Any,
    center_targets: Mapping[str, tuple[float, float]],
) -> tuple[float, float]:
    bbox = getattr(element, "bbox", None)
    if bbox is None:
        return (0.0, 0.0)

    current_center = (bbox.x + bbox.width / 2.0, bbox.y + bbox.height / 2.0)
    for element_id in _element_ids_for_translation(element):
        if element_id in center_targets:
            target_x, target_y = center_targets[element_id]
            return (target_x - current_center[0], target_y - current_center[1])
    return (0.0, 0.0)


def _motion_start_delta(
    element: Any,
    start_positions: Mapping[str, tuple[float, float]],
) -> tuple[float, float]:
    bbox = getattr(element, "bbox", None)
    if bbox is None:
        return (0.0, 0.0)

    for element_id in _element_ids_for_translation(element):
        if element_id in start_positions:
            target_x, target_y = start_positions[element_id]
            return (target_x - bbox.x, target_y - bbox.y)
    return (0.0, 0.0)


def _translate_element_to_center_target(
    element: Any,
    center_targets: Mapping[str, tuple[float, float]],
):
    from dataclasses import replace as _replace

    from svg2ooxml.ir.scene import Group

    dx, dy = _center_target_delta(element, center_targets)

    if isinstance(element, Group):
        moved_children = [
            _translate_element_to_center_target(child, center_targets)
            for child in element.children
        ]
        if _has_translation_delta(dx, dy):
            moved_children = [
                _translate_element_by_delta(child, dx, dy)
                for child in moved_children
            ]
        return _replace(element, children=moved_children)

    if not _has_translation_delta(dx, dy):
        return element
    return _translate_element_by_delta(element, dx, dy)


def _translate_element_to_motion_start(
    element: Any,
    start_positions: Mapping[str, tuple[float, float]],
):
    from dataclasses import replace as _replace

    from svg2ooxml.ir.scene import Group

    dx, dy = _motion_start_delta(element, start_positions)

    if isinstance(element, Group):
        moved_children = [
            _translate_element_to_motion_start(child, start_positions)
            for child in element.children
        ]
        if _has_translation_delta(dx, dy):
            moved_children = [
                _translate_element_by_delta(child, dx, dy)
                for child in moved_children
            ]
        return _replace(element, children=moved_children)

    if not _has_translation_delta(dx, dy):
        return element
    return _translate_element_by_delta(element, dx, dy)


def _translate_element_by_delta(element: Any, dx: float, dy: float):
    from dataclasses import replace as _replace

    from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect
    from svg2ooxml.ir.scene import Group, Image
    from svg2ooxml.ir.scene import Path as IRPath
    from svg2ooxml.ir.shapes import Circle, Ellipse, Line, Polygon, Polyline, Rectangle
    from svg2ooxml.ir.text import TextFrame

    def _move_point(point: Point) -> Point:
        return Point(point.x + dx, point.y + dy)

    def _move_rect(rect: Rect) -> Rect:
        return Rect(rect.x + dx, rect.y + dy, rect.width, rect.height)

    if isinstance(element, Group):
        return _replace(
            element,
            children=[
                _translate_element_by_delta(child, dx, dy)
                for child in element.children
            ],
        )
    if isinstance(element, IRPath):
        moved_segments = []
        for segment in element.segments:
            if isinstance(segment, LineSegment):
                moved_segments.append(
                    LineSegment(
                        start=_move_point(segment.start),
                        end=_move_point(segment.end),
                    )
                )
            elif isinstance(segment, BezierSegment):
                moved_segments.append(
                    BezierSegment(
                        start=_move_point(segment.start),
                        control1=_move_point(segment.control1),
                        control2=_move_point(segment.control2),
                        end=_move_point(segment.end),
                    )
                )
            else:
                moved_segments.append(segment)
        return _replace(element, segments=moved_segments)
    if isinstance(element, Rectangle):
        return _replace(element, bounds=_move_rect(element.bounds))
    if isinstance(element, Circle):
        return _replace(element, center=_move_point(element.center))
    if isinstance(element, Ellipse):
        return _replace(element, center=_move_point(element.center))
    if isinstance(element, Line):
        return _replace(
            element,
            start=_move_point(element.start),
            end=_move_point(element.end),
        )
    if isinstance(element, Polyline):
        return _replace(element, points=[_move_point(point) for point in element.points])
    if isinstance(element, Polygon):
        return _replace(element, points=[_move_point(point) for point in element.points])
    if isinstance(element, TextFrame):
        return _replace(
            element,
            origin=_move_point(element.origin),
            bbox=_move_rect(element.bbox),
        )
    if isinstance(element, Image):
        return _replace(element, origin=_move_point(element.origin))
    return element
