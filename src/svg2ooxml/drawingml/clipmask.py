"""Clip and mask rendering helpers for the DrawingML writer."""

from __future__ import annotations

from typing import Iterable, List, Tuple

from svg2ooxml.drawingml.generator import px_to_emu
from svg2ooxml.drawingml.mask_generator import compute_mask_geometry
from svg2ooxml.drawingml.paint_runtime import clip_rect_to_xml
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, Rect, SegmentType
from svg2ooxml.ir.scene import ClipRef, MaskRef
from svg2ooxml.parser.geometry.matrix import Matrix2D

POINT_EPSILON = 1e-6

__all__ = [
    "clip_xml_for",
    "mask_xml_for",
]


def clip_xml_for(clip_ref: ClipRef | None) -> Tuple[str, List[str]]:
    """Return clip-path XML plus diagnostics."""

    diagnostics: List[str] = []
    if clip_ref is None:
        return "", diagnostics

    if clip_ref.custom_geometry_xml:
        return clip_ref.custom_geometry_xml, diagnostics

    if clip_ref.path_segments:
        xml = _clip_path_from_segments(clip_ref.path_segments, clip_ref.transform)
        if xml:
            return xml, diagnostics

    bbox = getattr(clip_ref, "bounding_box", None)
    if isinstance(bbox, Rect):
        xml = clip_rect_to_xml(
            {
                "x": bbox.x,
                "y": bbox.y,
                "width": bbox.width,
                "height": bbox.height,
            }
        )
        return xml, diagnostics

    return "", diagnostics


def mask_xml_for(mask_ref: MaskRef | None) -> Tuple[str, List[str]]:
    """Return mask approximation XML plus diagnostics."""

    diagnostics: List[str] = []
    if mask_ref is None or mask_ref.definition is None:
        return "", diagnostics

    definition = mask_ref.definition
    geometry_result = compute_mask_geometry(mask_ref)
    if geometry_result is not None and geometry_result.diagnostics:
        diagnostics.extend(geometry_result.diagnostics)

    if (
        geometry_result is not None
        and geometry_result.geometry is not None
        and geometry_result.segments
    ):
        xml = _clip_path_from_segments(geometry_result.segments, None)
        if xml:
            diagnostics.append(f"Mask {definition.mask_id} emitted as clip path geometry.")
            return xml, diagnostics

    bbox = definition.bounding_box
    if isinstance(bbox, Rect):
        xml = clip_rect_to_xml(
            {
                "x": bbox.x,
                "y": bbox.y,
                "width": bbox.width,
                "height": bbox.height,
            }
        )
        if xml:
            diagnostics.append(f"Mask {definition.mask_id} approximated via bounding box clip.")
        return xml, diagnostics

    return "", diagnostics


def _clip_path_from_segments(
    segments: Iterable[SegmentType],
    transform,
) -> str:
    segment_list = [segment for segment in segments if isinstance(segment, (LineSegment, BezierSegment))]
    if not segment_list:
        return ""

    matrix = _coerce_matrix(transform)
    parts: List[str] = ["<a:clipPath>", "<a:path clipFill=\"1\">"]
    current_point: Point | None = None

    for segment in segment_list:
        start_pt = _transform_point(segment.start, matrix)
        if current_point is None or not _points_close(current_point, start_pt):
            parts.append(_move_to_xml(start_pt))
        if isinstance(segment, LineSegment):
            end_pt = _transform_point(segment.end, matrix)
            parts.append(_line_to_xml(end_pt))
            current_point = end_pt
        elif isinstance(segment, BezierSegment):
            control1 = _transform_point(segment.control1, matrix)
            control2 = _transform_point(segment.control2, matrix)
            end_pt = _transform_point(segment.end, matrix)
            parts.append(_cubic_to_xml(control1, control2, end_pt))
            current_point = end_pt

    parts.append("<a:close/>")
    parts.append("</a:path>")
    parts.append("</a:clipPath>")
    return "\n".join(parts)


def _coerce_matrix(transform) -> Matrix2D | None:
    if isinstance(transform, Matrix2D):
        return transform
    if isinstance(transform, (tuple, list)) and len(transform) == 6:
        try:
            values = [float(value) for value in transform]
        except (TypeError, ValueError):
            return None
        return Matrix2D(*values)
    return None


def _transform_point(point: Point, matrix: Matrix2D | None) -> Point:
    if matrix is None:
        return point
    return matrix.transform_point(point)


def _points_close(lhs: Point, rhs: Point, *, epsilon: float = POINT_EPSILON) -> bool:
    return abs(lhs.x - rhs.x) <= epsilon and abs(lhs.y - rhs.y) <= epsilon


def _move_to_xml(point: Point) -> str:
    x = px_to_emu(point.x)
    y = px_to_emu(point.y)
    return f'<a:moveTo><a:pt x="{x}" y="{y}"/></a:moveTo>'


def _line_to_xml(point: Point) -> str:
    x = px_to_emu(point.x)
    y = px_to_emu(point.y)
    return f'<a:lnTo><a:pt x="{x}" y="{y}"/></a:lnTo>'


def _cubic_to_xml(control1: Point, control2: Point, end: Point) -> str:
    c1x = px_to_emu(control1.x)
    c1y = px_to_emu(control1.y)
    c2x = px_to_emu(control2.x)
    c2y = px_to_emu(control2.y)
    ex = px_to_emu(end.x)
    ey = px_to_emu(end.y)
    return (
        "<a:cubicBezTo>"
        f'<a:pt x="{c1x}" y="{c1y}"/>'
        f'<a:pt x="{c2x}" y="{c2y}"/>'
        f'<a:pt x="{ex}" y="{ey}"/>'
        "</a:cubicBezTo>"
    )
