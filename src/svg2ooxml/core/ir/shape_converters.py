"""Shape conversion helpers for the IR converter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.common.svg_refs import local_name
from svg2ooxml.core.ir.shape.fallback_converter import ShapeFallbackPathMixin
from svg2ooxml.core.ir.shape.image_converter import ShapeImageMixin
from svg2ooxml.core.ir.shape.resvg_converter import ShapeResvgPathMixin
from svg2ooxml.core.ir.shape_converters_fallbacks import ShapeFallbackMixin
from svg2ooxml.core.ir.shape_converters_resvg import ShapeResvgMixin
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
from svg2ooxml.ir.paint import (
    LinearGradientPaint,
    PatternPaint,
    RadialGradientPaint,
    SolidPaint,
    Stroke,
)
from svg2ooxml.ir.scene import ClipRef, Group, Image, MaskInstance, MaskRef, Path
from svg2ooxml.ir.text import Run, TextAnchor, TextFrame
from svg2ooxml.policy.constants import FALLBACK_BITMAP, FALLBACK_EMF

_NATIVE_FILL_TYPES = (SolidPaint, LinearGradientPaint, RadialGradientPaint)


class ShapeConversionMixin(
    ShapeResvgMixin,
    ShapeFallbackMixin,
    ShapeResvgPathMixin,
    ShapeFallbackPathMixin,
    ShapeImageMixin,
):
    """Mixin that houses individual SVG element conversion helpers."""

    _logger = None  # populated by IRConverter

    def _trace_geometry_decision(
        self,
        element: etree._Element,
        decision: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        tracer = getattr(self, "_tracer", None)
        if tracer is None:
            return
        tag = ""
        if isinstance(element.tag, str):
            tag = local_name(element.tag)
        element_id = element.get("id") if hasattr(element, "get") else None
        tracer.record_geometry_decision(
            tag=tag,
            decision=decision,
            metadata=dict(metadata) if isinstance(metadata, dict) else metadata,
            element_id=element_id,
        )

    @staticmethod
    def _fill_can_render_natively(fill, metadata: dict[str, Any]) -> bool:
        if isinstance(fill, _NATIVE_FILL_TYPES):
            return True
        if not isinstance(fill, PatternPaint):
            return False

        policy = metadata.get("policy", {}) if isinstance(metadata, dict) else {}
        geometry_policy = policy.get("geometry", {}) if isinstance(policy, dict) else {}
        paint_policy = policy.get("paint", {}) if isinstance(policy, dict) else {}
        fill_policy = (
            paint_policy.get("fill", {}) if isinstance(paint_policy, dict) else {}
        )

        for entry in (fill_policy, geometry_policy):
            if isinstance(entry, dict) and entry.get("suggest_fallback") in {
                FALLBACK_EMF,
                FALLBACK_BITMAP,
            }:
                return False
        return True

    @staticmethod
    def _pattern_fill_requires_path_fallback(fill) -> bool:
        if not isinstance(fill, PatternPaint):
            return False
        if fill.tile_image or fill.tile_relationship_id:
            return False

        transform = fill.transform
        if transform is None:
            return False

        matrix = transform.tolist() if hasattr(transform, "tolist") else transform
        identity = (
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        )
        try:
            for row_idx, row in enumerate(matrix):
                for col_idx, value in enumerate(row):
                    if abs(float(value) - identity[row_idx][col_idx]) >= 1e-9:
                        return True
            return False
        except (TypeError, ValueError, IndexError):
            return True

    @staticmethod
    def _prefer_pattern_path_fallback(
        metadata: dict[str, Any],
        *,
        allow_emf_fallback: bool,
        allow_bitmap_fallback: bool,
    ) -> str | None:
        geometry_policy = metadata.setdefault("policy", {}).setdefault("geometry", {})
        if allow_bitmap_fallback:
            geometry_policy.setdefault("suggest_fallback", FALLBACK_BITMAP)
            return FALLBACK_BITMAP
        return None

    @staticmethod
    def _prefer_non_native_fill_fallback(
        fill,
        *,
        allow_emf_fallback: bool,
        allow_bitmap_fallback: bool,
    ) -> str | None:
        if isinstance(fill, PatternPaint):
            if allow_bitmap_fallback:
                return FALLBACK_BITMAP
            return None
        if allow_bitmap_fallback:
            return FALLBACK_BITMAP
        if allow_emf_fallback:
            return FALLBACK_EMF
        return None

    def _convert_use(
        self,
        *,
        element: etree._Element,
        coord_space: CoordinateSpace,
        current_navigation,
        traverse_callback,
    ):
        """Convert <use> elements via resvg only."""
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result
            resvg_lookup = getattr(self, "_resvg_element_lookup", {})
            resvg_node = (
                resvg_lookup.get(element) if isinstance(resvg_lookup, dict) else None
            )
            if type(resvg_node).__name__ == "TextNode":
                text_converter = getattr(self, "_text_converter", None)
                text_convert = getattr(text_converter, "convert", None)
                if callable(text_convert):
                    try:
                        text_result = text_convert(
                            element=element,
                            coord_space=coord_space,
                            resvg_node=resvg_node,
                        )
                    except Exception as exc:  # pragma: no cover - defensive logging
                        self._logger.debug(
                            "Resvg text conversion failed for %s: %s",
                            element.get("id") or "<use>",
                            exc,
                        )
                    else:
                        if text_result is not None:
                            return text_result
            use_target = self._resolve_use_target(element)
            use_target_tag = (
                _local_name(getattr(use_target, "tag", "")).lower()
                if use_target is not None
                else ""
            )
            if use_target_tag == "image":
                expanded_result = self.expand_use(
                    element=element,
                    coord_space=coord_space,
                    current_navigation=current_navigation,
                    traverse_callback=traverse_callback,
                )
                if expanded_result:
                    return expanded_result
            self._trace_resvg_only_miss(element, "resvg_conversion_failed")
            return None
        self._trace_resvg_only_miss(element, self._resvg_miss_reason(element))
        return None

    def _resolve_use_target(self, element: etree._Element) -> etree._Element | None:
        href_attr = element.get("{http://www.w3.org/1999/xlink}href") or element.get(
            "href"
        )
        if not href_attr:
            return None
        reference_id = self._normalize_href_reference(href_attr)
        if reference_id is None:
            return None

        symbol_definitions = getattr(self, "_symbol_definitions", {})
        target = (
            symbol_definitions.get(reference_id)
            if isinstance(symbol_definitions, dict)
            else None
        )
        if target is not None:
            return target

        element_index = getattr(self, "_element_index", {})
        if isinstance(element_index, dict):
            target = element_index.get(reference_id)
        return target if isinstance(target, etree._Element) else None

    def _convert_rect(self, *, element: etree._Element, coord_space: CoordinateSpace):
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result
            degenerate_fallback = self._convert_degenerate_shape_fallback(
                element=element,
                coord_space=coord_space,
            )
            if degenerate_fallback is not None:
                return degenerate_fallback
            self._trace_resvg_only_miss(element, "resvg_conversion_failed")
            return None
        self._trace_resvg_only_miss(element, self._resvg_miss_reason(element))
        return None

    def _convert_circle(self, *, element: etree._Element, coord_space: CoordinateSpace):
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result
            degenerate_fallback = self._convert_degenerate_shape_fallback(
                element=element,
                coord_space=coord_space,
            )
            if degenerate_fallback is not None:
                return degenerate_fallback
            self._trace_resvg_only_miss(element, "resvg_conversion_failed")
            return None
        self._trace_resvg_only_miss(element, self._resvg_miss_reason(element))
        return None

    def _convert_ellipse(
        self, *, element: etree._Element, coord_space: CoordinateSpace
    ):
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result
            degenerate_fallback = self._convert_degenerate_shape_fallback(
                element=element,
                coord_space=coord_space,
            )
            if degenerate_fallback is not None:
                return degenerate_fallback
            self._trace_resvg_only_miss(element, "resvg_conversion_failed")
            return None
        self._trace_resvg_only_miss(element, self._resvg_miss_reason(element))
        return None

    def _convert_line(self, *, element: etree._Element, coord_space: CoordinateSpace):
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result
            degenerate_fallback = self._convert_degenerate_shape_fallback(
                element=element,
                coord_space=coord_space,
            )
            if degenerate_fallback is not None:
                return degenerate_fallback
            self._trace_resvg_only_miss(element, "resvg_conversion_failed")
            return None
        self._trace_resvg_only_miss(element, self._resvg_miss_reason(element))
        return None

    def _convert_path(self, *, element: etree._Element, coord_space: CoordinateSpace):
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result
            self._trace_resvg_only_miss(element, "resvg_conversion_failed")
            return None
        self._trace_resvg_only_miss(element, self._resvg_miss_reason(element))
        return None

    def _convert_polygon(
        self, *, element: etree._Element, coord_space: CoordinateSpace
    ):
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result
            self._trace_resvg_only_miss(element, "resvg_conversion_failed")
            return None
        self._trace_resvg_only_miss(element, self._resvg_miss_reason(element))
        return None

    def _convert_polyline(
        self, *, element: etree._Element, coord_space: CoordinateSpace
    ):
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result
            self._trace_resvg_only_miss(element, "resvg_conversion_failed")
            return None
        self._trace_resvg_only_miss(element, self._resvg_miss_reason(element))
        return None

    def _convert_foreign_object(
        self,
        *,
        element: etree._Element,
        coord_space: CoordinateSpace,
        traverse_callback: Callable[[etree._Element, Any | None], list],
        current_navigation,
    ):
        conversion_context = getattr(self, "_conversion_context", None)
        width = self._resolve_length(
            element.get("width"), conversion_context, axis="x"
        )
        height = self._resolve_length(
            element.get("height"), conversion_context, axis="y"
        )
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
        transformed_points = [
            coord_space.apply_point(px, py) for (px, py) in rect_points
        ]
        bbox = _compute_bbox(transformed_points)

        payload = _first_foreign_child(element)
        payload_type = (
            _classify_foreign_payload(payload) if payload is not None else "empty"
        )
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
            placeholder = self._foreign_object_placeholder_with_opacity(
                bbox,
                clip_ref,
                mask_ref,
                mask_instance,
                metadata,
                opacity=style.opacity,
            )
            self._trace_geometry_decision(element, "placeholder", placeholder.metadata)
            self._trace_stage(
                "foreign_object_placeholder",
                stage="foreign_object",
                metadata=metadata.get("foreign_object"),
                subject=element.get("id"),
            )
            return placeholder

        if payload_type == "nested_svg":
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
                opacity=style.opacity,
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

        if payload_type == "image":
            href = _extract_image_href(payload)
            if not href:
                return self._foreign_object_placeholder_with_opacity(
                    bbox,
                    clip_ref,
                    mask_ref,
                    mask_instance,
                    metadata,
                    opacity=style.opacity,
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
                opacity=style.opacity,
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

        if payload_type == "xhtml":
            text_content = _collect_foreign_text(payload)
            if not text_content:
                placeholder = self._foreign_object_placeholder_with_opacity(
                    bbox,
                    clip_ref,
                    mask_ref,
                    mask_instance,
                    metadata,
                    opacity=style.opacity,
                )
                self._trace_geometry_decision(
                    element, "placeholder", placeholder.metadata
                )
                self._trace_stage(
                    "foreign_object_placeholder",
                    stage="foreign_object",
                    metadata=metadata.get("foreign_object"),
                    subject=element.get("id"),
                )
                return placeholder
            run = Run(
                text=text_content,
                font_family="Arial",
                font_size_pt=12.0,
                fill_opacity=style.opacity,
            )
            frame = TextFrame(
                origin=Point(bbox.x, bbox.y),
                anchor=TextAnchor.START,
                bbox=bbox,
                runs=[run],
                metadata=metadata,
            )
            # TextFrame doesn't have an 'opacity' field, but it's in metadata and runs?
            # Actually DrawingMLWriter handles text opacity per run.
            self._trace_geometry_decision(element, "native", frame.metadata)
            self._trace_stage(
                "foreign_object_text",
                stage="foreign_object",
                metadata={"character_count": len(text_content)},
                subject=element.get("id"),
            )
            return frame

        placeholder = self._foreign_object_placeholder_with_opacity(
            bbox,
            clip_ref,
            mask_ref,
            mask_instance,
            metadata,
            opacity=style.opacity,
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
        stroke = Stroke(
            paint=SolidPaint(rgb="999999", opacity=_clamp01(1.0)), width=1.0
        )
        placeholder_metadata = dict(metadata)
        path = Path(
            segments=segments,
            fill=fill,
            stroke=stroke,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=_clamp01(1.0),
            metadata=placeholder_metadata,
            effects=[],
        )
        self._process_mask_metadata(path)
        return path
