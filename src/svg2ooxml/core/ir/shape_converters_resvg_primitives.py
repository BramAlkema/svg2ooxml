"""Native primitive conversions for resvg-backed shape conversion."""

from __future__ import annotations

from typing import Any

from lxml import etree

from svg2ooxml.core.ir.shape_converters_utils import _uniform_scale
from svg2ooxml.core.styling.style_extractor import StyleResult
from svg2ooxml.core.traversal.constants import DEFAULT_TOLERANCE
from svg2ooxml.core.traversal.geometry_utils import (
    is_axis_aligned,
    scaled_corner_radius,
    transform_axis_aligned_rect,
)
from svg2ooxml.ir.geometry import Point
from svg2ooxml.ir.scene import ClipRef, MaskInstance, MaskRef
from svg2ooxml.ir.shapes import Circle, Ellipse, Rectangle


class ResvgPrimitiveSupportMixin:
    def _resvg_rect_to_rectangle(
        self,
        *,
        element: etree._Element,
        resvg_node: Any,
        style: StyleResult,
        metadata: dict[str, Any],
        clip_ref: ClipRef | None,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
    ) -> Rectangle | None:
        if clip_ref is not None or mask_ref is not None or mask_instance is not None:
            return None
        if style.effects:
            return None

        transform_matrix = self._matrix2d_from_resvg(
            getattr(resvg_node, "transform", None)
        )
        if not is_axis_aligned(transform_matrix, DEFAULT_TOLERANCE):
            return None

        x = self._coerce_float(getattr(resvg_node, "x", None), 0.0)
        y = self._coerce_float(getattr(resvg_node, "y", None), 0.0)
        width = self._coerce_float(getattr(resvg_node, "width", None), 0.0)
        height = self._coerce_float(getattr(resvg_node, "height", None), 0.0)

        bounds = transform_axis_aligned_rect(
            transform_matrix,
            x,
            y,
            width,
            height,
            DEFAULT_TOLERANCE,
        )
        if bounds is None:
            return None

        rx = self._coerce_float(getattr(resvg_node, "rx", None), 0.0)
        ry = self._coerce_float(getattr(resvg_node, "ry", None), 0.0)
        if rx <= 0.0 and ry > 0.0:
            rx = ry
        if ry <= 0.0 and rx > 0.0:
            ry = rx

        max_rx = getattr(resvg_node, "width", 0.0) / 2.0
        max_ry = getattr(resvg_node, "height", 0.0) / 2.0
        rx = max(0.0, min(rx, max_rx))
        ry = max(0.0, min(ry, max_ry))

        if rx > DEFAULT_TOLERANCE and ry > DEFAULT_TOLERANCE:
            if abs(rx - ry) > DEFAULT_TOLERANCE:
                return None
            corner_radius = scaled_corner_radius(rx, transform_matrix, DEFAULT_TOLERANCE)
        else:
            corner_radius = 0.0

        return Rectangle(
            bounds=bounds,
            corner_radius=corner_radius,
            fill=style.fill,
            stroke=style.stroke,
            opacity=style.opacity,
            effects=list(style.effects),
            metadata=metadata,
            element_id=element.get("id"),
        )

    def _resvg_circle_to_circle(
        self,
        *,
        element: etree._Element,
        resvg_node: Any,
        style: StyleResult,
        metadata: dict[str, Any],
        clip_ref: ClipRef | None,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
    ) -> Circle | None:
        if clip_ref is not None or mask_ref is not None or mask_instance is not None:
            return None
        if style.effects:
            return None

        transform_matrix = self._matrix2d_from_resvg(
            getattr(resvg_node, "transform", None)
        )
        cx = self._coerce_float(getattr(resvg_node, "cx", None), 0.0)
        cy = self._coerce_float(getattr(resvg_node, "cy", None), 0.0)
        raw_radius = self._coerce_float(getattr(resvg_node, "r", None), 0.0)
        if transform_matrix.is_identity(tolerance=DEFAULT_TOLERANCE):
            center = Point(cx, cy)
            scale = 1.0
        else:
            scale = _uniform_scale(transform_matrix, DEFAULT_TOLERANCE)
            if scale is None:
                return None
            center = transform_matrix.transform_point(Point(cx, cy))

        radius = raw_radius * scale
        if radius <= DEFAULT_TOLERANCE:
            return None

        return Circle(
            center=center,
            radius=radius,
            fill=style.fill,
            stroke=style.stroke,
            opacity=style.opacity,
            effects=list(style.effects),
            metadata=metadata,
            element_id=element.get("id"),
        )

    def _resvg_ellipse_to_ellipse(
        self,
        *,
        element: etree._Element,
        resvg_node: Any,
        style: StyleResult,
        metadata: dict[str, Any],
        clip_ref: ClipRef | None,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
    ) -> Ellipse | None:
        if clip_ref is not None or mask_ref is not None or mask_instance is not None:
            return None
        if style.effects:
            return None

        transform_matrix = self._matrix2d_from_resvg(
            getattr(resvg_node, "transform", None)
        )
        has_rotation = (
            abs(transform_matrix.b) > DEFAULT_TOLERANCE
            or abs(transform_matrix.c) > DEFAULT_TOLERANCE
        )
        if has_rotation:
            return None

        scale_x = float(transform_matrix.a)
        scale_y = float(transform_matrix.d)
        translate_x = float(transform_matrix.e)
        translate_y = float(transform_matrix.f)

        cx = self._coerce_float(getattr(resvg_node, "cx", None), 0.0)
        cy = self._coerce_float(getattr(resvg_node, "cy", None), 0.0)
        raw_rx = self._coerce_float(getattr(resvg_node, "rx", None), 0.0)
        raw_ry = self._coerce_float(getattr(resvg_node, "ry", None), 0.0)

        if transform_matrix.is_identity(tolerance=DEFAULT_TOLERANCE):
            center = Point(cx, cy)
            radius_x = raw_rx
            radius_y = raw_ry
        else:
            if abs(scale_x) <= DEFAULT_TOLERANCE or abs(scale_y) <= DEFAULT_TOLERANCE:
                return None
            center = Point(cx * scale_x + translate_x, cy * scale_y + translate_y)
            radius_x = abs(raw_rx * scale_x)
            radius_y = abs(raw_ry * scale_y)

        if radius_x <= DEFAULT_TOLERANCE or radius_y <= DEFAULT_TOLERANCE:
            return None

        return Ellipse(
            center=center,
            radius_x=radius_x,
            radius_y=radius_y,
            fill=style.fill,
            stroke=style.stroke,
            opacity=style.opacity,
            effects=list(style.effects),
            metadata=metadata,
            element_id=element.get("id"),
        )


__all__ = ["ResvgPrimitiveSupportMixin"]
