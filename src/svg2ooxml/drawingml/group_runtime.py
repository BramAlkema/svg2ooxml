"""Group rendering helpers for DrawingML writer."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from svg2ooxml.drawingml.generator import px_to_emu
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect
from svg2ooxml.ir.scene import Group
from svg2ooxml.ir.scene import Image as IRImage
from svg2ooxml.ir.scene import Path as IRPath
from svg2ooxml.ir.shapes import Circle, Ellipse, Line, Polygon, Polyline, Rectangle
from svg2ooxml.ir.text import TextFrame as IRTextFrame


def children_overlap(children) -> bool:
    """Return True if any two children have overlapping bounding boxes."""
    bboxes = []
    for child in children:
        bbox = getattr(child, "bbox", None)
        if bbox is not None and bbox.width > 0 and bbox.height > 0:
            bboxes.append(bbox)
    for i in range(len(bboxes)):
        for j in range(i + 1, len(bboxes)):
            a, b = bboxes[i], bboxes[j]
            if a.x < b.x + b.width and a.x + a.width > b.x and a.y < b.y + b.height and a.y + a.height > b.y:
                return True
    return False


def element_ids_for(element: object) -> set[str]:
    element_ids: set[str] = set()
    metadata = getattr(element, "metadata", None)
    if isinstance(metadata, dict):
        ids = metadata.get("element_ids")
        if isinstance(ids, (list, tuple, set)):
            element_ids.update(str(element_id) for element_id in ids if isinstance(element_id, str))
    element_id = getattr(element, "element_id", None)
    if isinstance(element_id, str) and element_id:
        element_ids.add(element_id)
    return element_ids


def translate_group_child_to_local_coordinates(element, dx: float, dy: float):
    """Return a copy of *element* translated by ``(-dx, -dy)`` for grpSp output."""
    if abs(dx) <= 1e-9 and abs(dy) <= 1e-9:
        return element

    def _move_point(point: Point) -> Point:
        return Point(point.x - dx, point.y - dy)

    def _move_rect(rect: Rect) -> Rect:
        return Rect(rect.x - dx, rect.y - dy, rect.width, rect.height)

    if isinstance(element, Group):
        return replace(
            element,
            children=[translate_group_child_to_local_coordinates(child, dx, dy) for child in element.children],
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
        return replace(element, segments=moved_segments)
    if isinstance(element, Rectangle):
        return replace(element, bounds=_move_rect(element.bounds))
    if isinstance(element, Circle):
        return replace(element, center=_move_point(element.center))
    if isinstance(element, Ellipse):
        return replace(element, center=_move_point(element.center))
    if isinstance(element, Line):
        return replace(
            element,
            start=_move_point(element.start),
            end=_move_point(element.end),
        )
    if isinstance(element, Polyline):
        return replace(element, points=[_move_point(point) for point in element.points])
    if isinstance(element, Polygon):
        return replace(element, points=[_move_point(point) for point in element.points])
    if isinstance(element, IRTextFrame):
        return replace(
            element,
            origin=_move_point(element.origin),
            bbox=_move_rect(element.bbox),
        )
    if isinstance(element, IRImage):
        return replace(element, origin=_move_point(element.origin))
    return element


def apply_group_wrapper_semantics(
    group: Group,
    group_metadata: dict[str, object],
) -> list:
    return [_apply_group_wrapper_semantics_to_child(child, group, group_metadata) for child in group.children]


def group_xfrm_xml(group: Group) -> str:
    bbox = group.bbox
    x = px_to_emu(bbox.x)
    y = px_to_emu(bbox.y)
    width = px_to_emu(bbox.width)
    height = px_to_emu(bbox.height)
    return (
        f"<a:xfrm>"
        f'<a:off x="{x}" y="{y}"/>'
        f'<a:ext cx="{width}" cy="{height}"/>'
        f'<a:chOff x="0" y="0"/>'
        f'<a:chExt cx="{width}" cy="{height}"/>'
        f"</a:xfrm>"
    )


def can_remove_group_wrapper(group: Group) -> bool:
    if abs(group.opacity - 1.0) > 1e-9:
        return False
    if group.clip is not None or group.mask is not None or group.mask_instance is not None:
        return False
    metadata = group.metadata if isinstance(group.metadata, dict) else {}
    if metadata.get("filters") or metadata.get("filter_metadata"):
        return False
    return True


def group_contains_animation_target(
    group: Group,
    metadata_targets_animation: Callable[[object], bool],
) -> bool:
    if metadata_targets_animation(group.metadata):
        return True
    for child in group.children:
        metadata = getattr(child, "metadata", None)
        if metadata_targets_animation(metadata):
            return True
        if isinstance(child, Group) and group_contains_animation_target(child, metadata_targets_animation):
            return True
    return False


def should_flatten_group_for_native_animation(
    group: Group,
    metadata_targets_animation: Callable[[object], bool],
) -> bool:
    if not can_remove_group_wrapper(group):
        return False
    if metadata_targets_animation(group.metadata):
        return False
    return group_contains_bookmark_navigation(group) or group_contains_animation_target(group, metadata_targets_animation)


def group_contains_bookmark_navigation(group: Group) -> bool:
    if metadata_has_bookmark_navigation(group.metadata):
        return True
    for child in group.children:
        metadata = getattr(child, "metadata", None)
        if metadata_has_bookmark_navigation(metadata):
            return True
        if isinstance(child, Group) and group_contains_bookmark_navigation(child):
            return True
    return False


def metadata_has_bookmark_navigation(metadata: object) -> bool:
    if not isinstance(metadata, dict):
        return False
    navigation = metadata.get("navigation")
    if navigation is None:
        return False
    entries = navigation if isinstance(navigation, list) else [navigation]
    for entry in entries:
        if isinstance(entry, dict) and entry.get("kind") == "bookmark":
            return True
    return False


def _multiply_element_opacity(element, opacity: float):
    if opacity >= 0.999:
        return element
    current = getattr(element, "opacity", None)
    if not isinstance(current, (int, float)):
        return element
    try:
        return replace(element, opacity=max(0.0, min(1.0, float(current) * opacity)))
    except TypeError:
        return element


def _metadata_with_group_semantics(
    child_metadata: object,
    group_metadata: dict[str, object],
) -> dict[str, object]:
    metadata = dict(child_metadata) if isinstance(child_metadata, dict) else {}
    clip_bounds = group_metadata.get("_clip_bounds")
    if clip_bounds is not None and "_clip_bounds" not in metadata:
        metadata["_clip_bounds"] = clip_bounds
    navigation = group_metadata.get("navigation")
    if navigation is not None and "navigation" not in metadata:
        metadata["navigation"] = navigation
    return metadata


def _apply_group_wrapper_semantics_to_child(
    child,
    group: Group,
    group_metadata: dict[str, object],
):
    wrapped = _multiply_element_opacity(child, group.opacity)
    metadata = _metadata_with_group_semantics(
        getattr(wrapped, "metadata", None),
        group_metadata,
    )
    try:
        return replace(wrapped, metadata=metadata)
    except TypeError:
        return wrapped


__all__ = [
    "apply_group_wrapper_semantics",
    "can_remove_group_wrapper",
    "children_overlap",
    "element_ids_for",
    "group_contains_animation_target",
    "group_contains_bookmark_navigation",
    "group_xfrm_xml",
    "metadata_has_bookmark_navigation",
    "should_flatten_group_for_native_animation",
    "translate_group_child_to_local_coordinates",
]
