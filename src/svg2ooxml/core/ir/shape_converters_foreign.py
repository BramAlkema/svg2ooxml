"""foreignObject conversion helpers for SVG shape conversion."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.core.ir.shape_converters_utils import (
    _clamp01,
    _classify_foreign_payload,
    _collect_foreign_text,
    _compute_bbox,
    _extract_image_href,
    _first_foreign_child,
    _foreign_object_clip_id,
    _guess_image_format,
    _local_name,
    _rect_segments_from_bbox,
)
from svg2ooxml.core.styling import style_runtime as styles_runtime
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.paint import SolidPaint, Stroke
from svg2ooxml.ir.scene import ClipRef, Group, Image, MaskInstance, MaskRef, Path
from svg2ooxml.ir.text import Run, TextAnchor, TextFrame


class ShapeForeignObjectMixin:
    def _convert_foreign_object(
        self,
        *,
        element: etree._Element,
        coord_space: CoordinateSpace,
        traverse_callback: Callable[[etree._Element, Any | None], list],
        current_navigation,
    ):
        conversion_context = getattr(self, "_conversion_context", None)
        width = self._resolve_length(element.get("width"), conversion_context, axis="x")
        height = self._resolve_length(element.get("height"), conversion_context, axis="y")
        if width is None or height is None or width <= 0 or height <= 0:
            self._trace_stage(
                "foreign_object_dropped",
                stage="foreign_object",
                metadata={
                    "reason": "invalid_dimensions",
                    "width": element.get("width"),
                    "height": element.get("height"),
                },
                subject=element.get("id"),
            )
            return None
        x = self._resolve_length(element.get("x"), conversion_context, axis="x")
        y = self._resolve_length(element.get("y"), conversion_context, axis="y")

        rect_points = [
            (x, y),
            (x + width, y),
            (x + width, y + height),
            (x, y + height),
        ]
        transformed_points = [coord_space.apply_point(px, py) for (px, py) in rect_points]
        bbox = _compute_bbox(transformed_points)

        payload = _first_foreign_child(element)
        payload_type = _classify_foreign_payload(payload) if payload is not None else "empty"
        style = styles_runtime.extract_style(self, element)
        style = self._style_with_local_opacity(element, style)

        metadata: dict[str, Any] = {
            "foreign_object": {
                "payload_type": payload_type,
                "source_tag": _local_name(payload.tag) if payload is not None else None,
            }
        }
        clip_ref = ClipRef(
            clip_id=_foreign_object_clip_id(element, bbox),
            bounding_box=bbox,
        )
        mask_ref, mask_instance = self._resolve_mask_ref(element)

        if payload is None:
            return self._trace_foreign_placeholder(
                element,
                bbox,
                clip_ref,
                mask_ref,
                mask_instance,
                metadata,
                opacity=style.opacity,
            )

        if payload_type == "nested_svg":
            return self._convert_nested_svg_foreign_object(
                element,
                payload,
                coord_space,
                traverse_callback,
                current_navigation,
                x,
                y,
                clip_ref,
                mask_ref,
                mask_instance,
                style.opacity,
                metadata,
            )

        if payload_type == "image":
            return self._convert_image_foreign_object(
                element,
                payload,
                bbox,
                clip_ref,
                mask_ref,
                mask_instance,
                style.opacity,
                metadata,
            )

        if payload_type == "xhtml":
            return self._convert_xhtml_foreign_object(
                element,
                payload,
                bbox,
                clip_ref,
                mask_ref,
                mask_instance,
                style.opacity,
                metadata,
            )

        return self._trace_foreign_placeholder(
            element,
            bbox,
            clip_ref,
            mask_ref,
            mask_instance,
            metadata,
            opacity=style.opacity,
        )

    def _convert_nested_svg_foreign_object(
        self,
        element: etree._Element,
        payload: etree._Element,
        coord_space: CoordinateSpace,
        traverse_callback: Callable[[etree._Element, Any | None], list],
        current_navigation,
        x: float,
        y: float,
        clip_ref: ClipRef,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
        opacity: float,
        metadata: dict[str, Any],
    ):
        translation = Matrix2D(e=x, f=y)
        coord_space.push(translation)
        try:
            children = traverse_callback(payload, current_navigation)
        finally:
            coord_space.pop()
        if not children:
            return None
        group = Group(
            children=children,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=opacity,
            metadata=metadata,
        )
        self._process_mask_metadata(group)
        self._trace_geometry_decision(element, "native", group.metadata)
        self._trace_stage(
            "foreign_object_nested_svg",
            stage="foreign_object",
            metadata={"child_count": len(children)},
            subject=element.get("id"),
        )
        return group

    def _convert_image_foreign_object(
        self,
        element: etree._Element,
        payload: etree._Element,
        bbox: Rect,
        clip_ref: ClipRef,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
        opacity: float,
        metadata: dict[str, Any],
    ):
        href = _extract_image_href(payload)
        if not href:
            return self._foreign_object_placeholder_with_opacity(
                bbox,
                clip_ref,
                mask_ref,
                mask_instance,
                metadata,
                opacity=opacity,
            )

        image_metadata = dict(metadata)
        image_metadata.setdefault("foreign_object", {}).setdefault("href", href)
        format_hint = _guess_image_format(href, None, None)
        image = Image(
            origin=Point(bbox.x, bbox.y),
            size=bbox,
            data=None,
            format=format_hint,
            href=href,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=opacity,
            transform=None,
            metadata=image_metadata,
        )
        self._process_mask_metadata(image)
        self._trace_geometry_decision(element, "native", image.metadata)
        self._trace_stage(
            "foreign_object_image",
            stage="foreign_object",
            metadata={"href": href, "format": format_hint},
            subject=element.get("id"),
        )
        return image

    def _convert_xhtml_foreign_object(
        self,
        element: etree._Element,
        payload: etree._Element,
        bbox: Rect,
        clip_ref: ClipRef,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
        opacity: float,
        metadata: dict[str, Any],
    ):
        text_content = _collect_foreign_text(payload)
        if not text_content:
            return self._trace_foreign_placeholder(
                element,
                bbox,
                clip_ref,
                mask_ref,
                mask_instance,
                metadata,
                opacity=opacity,
            )
        run = Run(
            text=text_content,
            font_family="Arial",
            font_size_pt=12.0,
            fill_opacity=opacity,
        )
        frame = TextFrame(
            origin=Point(bbox.x, bbox.y),
            anchor=TextAnchor.START,
            bbox=bbox,
            runs=[run],
            metadata=metadata,
        )
        self._trace_geometry_decision(element, "native", frame.metadata)
        self._trace_stage(
            "foreign_object_text",
            stage="foreign_object",
            metadata={"character_count": len(text_content)},
            subject=element.get("id"),
        )
        return frame

    def _trace_foreign_placeholder(
        self,
        element: etree._Element,
        bbox: Rect,
        clip_ref: ClipRef,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
        metadata: dict[str, Any],
        *,
        opacity: float,
    ) -> Path:
        placeholder = self._foreign_object_placeholder_with_opacity(
            bbox,
            clip_ref,
            mask_ref,
            mask_instance,
            metadata,
            opacity=opacity,
        )
        self._trace_geometry_decision(element, "placeholder", placeholder.metadata)
        self._trace_stage(
            "foreign_object_placeholder",
            stage="foreign_object",
            metadata=metadata.get("foreign_object"),
            subject=element.get("id"),
        )
        return placeholder

    def _foreign_object_placeholder_with_opacity(
        self,
        bbox: Rect,
        clip_ref: ClipRef,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
        metadata: dict[str, Any],
        *,
        opacity: float,
    ) -> Path:
        placeholder = self._foreign_object_placeholder(
            bbox, clip_ref, mask_ref, mask_instance, metadata
        )
        return replace(placeholder, opacity=opacity)

    def _foreign_object_placeholder(
        self,
        bbox: Rect,
        clip_ref: ClipRef,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
        metadata: dict[str, Any],
    ) -> Path:
        segments = _rect_segments_from_bbox(bbox)
        fill = SolidPaint(rgb="F0F0F0", opacity=_clamp01(0.4))
        stroke = Stroke(paint=SolidPaint(rgb="999999", opacity=_clamp01(1.0)), width=1.0)
        path = Path(
            segments=segments,
            fill=fill,
            stroke=stroke,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=_clamp01(1.0),
            metadata=dict(metadata),
            effects=[],
        )
        self._process_mask_metadata(path)
        return path


__all__ = ["ShapeForeignObjectMixin"]
