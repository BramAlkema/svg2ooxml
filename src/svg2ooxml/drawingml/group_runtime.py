"""Group rendering helpers for DrawingML writer."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace

from svg2ooxml.drawingml.generator import px_to_emu
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect
from svg2ooxml.ir.paint import SolidPaint
from svg2ooxml.ir.scene import ClipRef, Group, MaskInstance, MaskRef
from svg2ooxml.ir.scene import Image as IRImage
from svg2ooxml.ir.scene import Path as IRPath
from svg2ooxml.ir.shapes import Circle, Ellipse, Line, Polygon, Polyline, Rectangle
from svg2ooxml.ir.text import TextFrame as IRTextFrame

from .skia_path import skia


def children_overlap(children) -> bool:
    """Return True if any two children have overlapping rendered bounds."""
    footprints = []
    for child in children:
        bbox = rendered_child_bounds(child)
        if bbox is not None:
            footprints.append((child, bbox))
    for i in range(len(footprints)):
        for j in range(i + 1, len(footprints)):
            child_a, bbox_a = footprints[i]
            child_b, bbox_b = footprints[j]
            if _rendered_children_overlap(child_a, bbox_a, child_b, bbox_b):
                return True
    return False


def rendered_child_bounds(child) -> Rect | None:
    """Return the visible footprint used for group opacity overlap decisions."""
    if not _has_visible_opacity(child):
        return None

    if isinstance(child, Group):
        boxes = [rendered_child_bounds(grandchild) for grandchild in child.children]
        return _union_rects([box for box in boxes if box is not None])

    bbox = getattr(child, "bbox", None)
    if not isinstance(bbox, Rect):
        return None

    visible_fill = _has_visible_fill(child)
    visible_stroke = _visible_stroke_width(child)
    if (
        not visible_fill
        and visible_stroke <= 0.0
        and not _has_nonpaint_visual_content(child)
    ):
        return None

    if visible_stroke > 0.0:
        bbox = _inflate_rect(bbox, visible_stroke / 2.0)

    if bbox.width <= 0.0 or bbox.height <= 0.0:
        return None
    return bbox


def _has_visible_opacity(child) -> bool:
    opacity = getattr(child, "opacity", 1.0)
    return not isinstance(opacity, (int, float)) or float(opacity) > 1e-6


def _has_visible_fill(child) -> bool:
    fill = getattr(child, "fill", None)
    if fill is None:
        return False
    if isinstance(fill, SolidPaint):
        return fill.opacity > 1e-6
    return True


def _visible_stroke_width(child) -> float:
    stroke = getattr(child, "stroke", None)
    if stroke is None:
        return 0.0
    paint = getattr(stroke, "paint", None)
    if paint is None:
        return 0.0
    if isinstance(paint, SolidPaint) and paint.opacity <= 1e-6:
        return 0.0
    opacity = getattr(stroke, "opacity", 1.0)
    if isinstance(opacity, (int, float)) and float(opacity) <= 1e-6:
        return 0.0
    width = getattr(stroke, "width", 0.0)
    return max(0.0, float(width)) if isinstance(width, (int, float)) else 0.0


def _has_nonpaint_visual_content(child) -> bool:
    return isinstance(child, (IRImage, IRTextFrame)) or bool(
        getattr(child, "effects", None)
    )


def _rendered_children_overlap(child_a, bbox_a: Rect, child_b, bbox_b: Rect) -> bool:
    if not _rects_overlap(bbox_a, bbox_b):
        return False
    exact_overlap = _exact_simple_overlap(child_a, child_b)
    return True if exact_overlap is None else exact_overlap


def _exact_simple_overlap(child_a, child_b) -> bool | None:
    if _is_exact_filled_circle(child_a) and _is_exact_filled_circle(child_b):
        return _circles_overlap(child_a, child_b)
    return None


def _is_exact_filled_circle(child) -> bool:
    return (
        isinstance(child, Circle)
        and child.radius > 0.0
        and _has_visible_fill(child)
        and _visible_stroke_width(child) <= 0.0
        and not _has_nonpaint_visual_content(child)
    )


def _circles_overlap(a: Circle, b: Circle) -> bool:
    dx = a.center.x - b.center.x
    dy = a.center.y - b.center.y
    radius_sum = a.radius + b.radius
    return dx * dx + dy * dy < radius_sum * radius_sum


def _rects_overlap(a: Rect, b: Rect) -> bool:
    return (
        a.x < b.x + b.width
        and a.x + a.width > b.x
        and a.y < b.y + b.height
        and a.y + a.height > b.y
    )


def _inflate_rect(rect: Rect, amount: float) -> Rect:
    if amount <= 0.0:
        return rect
    return Rect(
        rect.x - amount,
        rect.y - amount,
        rect.width + amount * 2.0,
        rect.height + amount * 2.0,
    )


def _union_rects(rects: list[Rect]) -> Rect | None:
    if not rects:
        return None
    min_x = min(rect.x for rect in rects)
    min_y = min(rect.y for rect in rects)
    max_x = max(rect.x + rect.width for rect in rects)
    max_y = max(rect.y + rect.height for rect in rects)
    return Rect(min_x, min_y, max_x - min_x, max_y - min_y)


def element_ids_for(element: object) -> set[str]:
    element_ids: set[str] = set()
    metadata = getattr(element, "metadata", None)
    if isinstance(metadata, dict):
        ids = metadata.get("element_ids")
        if isinstance(ids, (list, tuple, set)):
            element_ids.update(
                str(element_id) for element_id in ids if isinstance(element_id, str)
            )
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
            children=[
                translate_group_child_to_local_coordinates(child, dx, dy)
                for child in element.children
            ],
            clip=_move_clip_ref(element.clip, dx, dy),
            mask=_move_mask_ref(element.mask, dx, dy),
            mask_instance=_move_mask_instance(element.mask_instance, dx, dy),
            metadata=_move_metadata(element.metadata, dx, dy),
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
        return replace(
            element,
            segments=moved_segments,
            clip=_move_clip_ref(element.clip, dx, dy),
            mask=_move_mask_ref(element.mask, dx, dy),
            mask_instance=_move_mask_instance(element.mask_instance, dx, dy),
            metadata=_move_metadata(element.metadata, dx, dy),
        )
    if isinstance(element, Rectangle):
        return replace(
            element,
            bounds=_move_rect(element.bounds),
            metadata=_move_metadata(element.metadata, dx, dy),
        )
    if isinstance(element, Circle):
        return replace(
            element,
            center=_move_point(element.center),
            metadata=_move_metadata(element.metadata, dx, dy),
        )
    if isinstance(element, Ellipse):
        return replace(
            element,
            center=_move_point(element.center),
            metadata=_move_metadata(element.metadata, dx, dy),
        )
    if isinstance(element, Line):
        return replace(
            element,
            start=_move_point(element.start),
            end=_move_point(element.end),
            metadata=_move_metadata(element.metadata, dx, dy),
        )
    if isinstance(element, Polyline):
        return replace(
            element,
            points=[_move_point(point) for point in element.points],
            metadata=_move_metadata(element.metadata, dx, dy),
        )
    if isinstance(element, Polygon):
        return replace(
            element,
            points=[_move_point(point) for point in element.points],
            metadata=_move_metadata(element.metadata, dx, dy),
        )
    if isinstance(element, IRTextFrame):
        return replace(
            element,
            origin=_move_point(element.origin),
            bbox=_move_rect(element.bbox),
            metadata=_move_metadata(element.metadata, dx, dy),
        )
    if isinstance(element, IRImage):
        return replace(
            element,
            origin=_move_point(element.origin),
            clip=_move_clip_ref(element.clip, dx, dy),
            mask=_move_mask_ref(element.mask, dx, dy),
            mask_instance=_move_mask_instance(element.mask_instance, dx, dy),
            metadata=_move_metadata(element.metadata, dx, dy),
        )
    return element


def _move_clip_ref(clip: ClipRef | None, dx: float, dy: float) -> ClipRef | None:
    if clip is None:
        return None
    return replace(
        clip,
        bounding_box=_move_rect_or_none(clip.bounding_box, dx, dy),
        custom_geometry_bounds=_move_rect_or_none(clip.custom_geometry_bounds, dx, dy),
        skia_path=_move_skia_path(getattr(clip, "skia_path", None), dx, dy),
    )


def _move_mask_ref(mask: MaskRef | None, dx: float, dy: float) -> MaskRef | None:
    if mask is None:
        return None
    return replace(
        mask,
        target_bounds=_move_rect_or_none(mask.target_bounds, dx, dy),
    )


def _move_mask_instance(
    mask_instance: MaskInstance | None,
    dx: float,
    dy: float,
) -> MaskInstance | None:
    if mask_instance is None:
        return None
    return replace(
        mask_instance,
        mask=_move_mask_ref(mask_instance.mask, dx, dy),
        bounds=_move_rect_or_none(mask_instance.bounds, dx, dy),
    )


def _move_metadata(
    metadata: dict[str, object], dx: float, dy: float
) -> dict[str, object]:
    moved = dict(metadata)
    per_char = moved.get("per_char")
    if isinstance(per_char, dict):
        moved_per_char = dict(per_char)
        if "abs_x" in moved_per_char:
            moved_per_char["abs_x"] = _move_numeric_sequence(
                moved_per_char.get("abs_x"),
                dx,
            )
        if "abs_y" in moved_per_char:
            moved_per_char["abs_y"] = _move_numeric_sequence(
                moved_per_char.get("abs_y"),
                dy,
            )
        moved["per_char"] = moved_per_char
    if "_clip_bounds" in moved:
        moved["_clip_bounds"] = _move_rect_like(moved["_clip_bounds"], dx, dy)
    mask_meta = moved.get("mask")
    if isinstance(mask_meta, dict):
        moved["mask"] = _move_mask_metadata(mask_meta, dx, dy)
    filter_metadata = moved.get("filter_metadata")
    if isinstance(filter_metadata, dict):
        moved["filter_metadata"] = _move_filter_metadata(filter_metadata, dx, dy)
    return moved


def _move_mask_metadata(
    mask_meta: Mapping[str, object],
    dx: float,
    dy: float,
) -> dict[str, object]:
    moved = dict(mask_meta)
    for key in ("target_bounds", "instance_bounds"):
        if key in moved:
            moved[key] = _move_rect_like(moved[key], dx, dy)
    return moved


def _move_filter_metadata(
    filter_metadata: Mapping[str, object],
    dx: float,
    dy: float,
) -> dict[str, object]:
    moved: dict[str, object] = {}
    for filter_id, raw_meta in filter_metadata.items():
        if isinstance(raw_meta, dict):
            meta = dict(raw_meta)
            if "bounds" in meta:
                meta["bounds"] = _move_bounds_mapping(meta["bounds"], dx, dy)
            moved[str(filter_id)] = meta
        else:
            moved[str(filter_id)] = raw_meta
    return moved


def _move_rect_or_none(rect: Rect | None, dx: float, dy: float) -> Rect | None:
    if rect is None:
        return None
    return Rect(rect.x - dx, rect.y - dy, rect.width, rect.height)


def _move_skia_path(path, dx: float, dy: float):
    if path is None or skia is None:
        return path
    try:
        moved = skia.Path(path)
        matrix = skia.Matrix.Translate(float(-dx), float(-dy))
        moved.transform(matrix)
        return moved
    except Exception:
        return path


def _move_rect_like(value: object, dx: float, dy: float) -> object:
    if isinstance(value, Rect):
        return _move_rect_or_none(value, dx, dy)
    return _move_bounds_mapping(value, dx, dy)


def _move_bounds_mapping(value: object, dx: float, dy: float) -> object:
    if isinstance(value, Mapping):
        moved: dict[str, object] = dict(value)
        moved["x"] = _move_numeric_value(moved.get("x"), dx)
        moved["y"] = _move_numeric_value(moved.get("y"), dy)
        return moved
    if isinstance(value, tuple) and len(value) >= 2:
        return _move_position_tuple(value, dx, dy)
    if isinstance(value, list) and len(value) >= 2:
        return list(_move_position_tuple(tuple(value), dx, dy))
    return value


def _move_position_tuple(
    values: tuple[object, ...], dx: float, dy: float
) -> tuple[object, ...]:
    moved = list(values)
    moved[0] = _move_numeric_value(moved[0], dx)
    moved[1] = _move_numeric_value(moved[1], dy)
    return tuple(moved)


def _move_numeric_value(value: object, delta: float) -> object:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value - delta
    return value


def _move_numeric_sequence(values: object, delta: float) -> object:
    if not isinstance(values, list):
        return values
    return [_move_numeric_value(value, delta) for value in values]


def apply_group_wrapper_semantics(
    group: Group,
    group_metadata: dict[str, object],
) -> list:
    return [
        _apply_group_wrapper_semantics_to_child(child, group, group_metadata)
        for child in group.children
    ]


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
    if (
        group.clip is not None
        or group.mask is not None
        or group.mask_instance is not None
    ):
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
        if isinstance(child, Group) and group_contains_animation_target(
            child, metadata_targets_animation
        ):
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
    return group_contains_bookmark_navigation(group) or group_contains_animation_target(
        group, metadata_targets_animation
    )


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
    "rendered_child_bounds",
    "should_flatten_group_for_native_animation",
    "translate_group_child_to_local_coordinates",
]
