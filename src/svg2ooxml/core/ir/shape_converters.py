"""Shape conversion helpers for the IR converter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path as FsPath
from typing import Any

from lxml import etree

from svg2ooxml.common.geometry import Matrix2D
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
    _parse_float,
    _rect_segments_from_bbox,
)
from svg2ooxml.core.styling import style_runtime as styles_runtime
from svg2ooxml.core.styling.style_extractor import StyleResult
from svg2ooxml.core.traversal.constants import DEFAULT_TOLERANCE
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.ir.geometry import LineSegment, Point, Rect, SegmentType
from svg2ooxml.ir.paint import SolidPaint, Stroke
from svg2ooxml.ir.scene import ClipRef, Group, Image, MaskInstance, MaskRef, Path
from svg2ooxml.ir.text import Run, TextAnchor, TextFrame
from svg2ooxml.policy.constants import FALLBACK_BITMAP, FALLBACK_EMF
from svg2ooxml.policy.geometry import apply_geometry_policy
from svg2ooxml.services.image_service import ImageResource, ImageService


class ShapeConversionMixin(ShapeResvgMixin, ShapeFallbackMixin):
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
            tag = element.tag.split("}", 1)[-1]
        element_id = element.get("id") if hasattr(element, "get") else None
        tracer.record_geometry_decision(
            tag=tag,
            decision=decision,
            metadata=dict(metadata) if isinstance(metadata, dict) else metadata,
            element_id=element_id,
        )

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
            resvg_node = resvg_lookup.get(element) if isinstance(resvg_lookup, dict) else None
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
            use_target_tag = _local_name(getattr(use_target, "tag", "")).lower() if use_target is not None else ""
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
        href_attr = element.get("{http://www.w3.org/1999/xlink}href") or element.get("href")
        if not href_attr:
            return None
        reference_id = self._normalize_href_reference(href_attr)
        if reference_id is None:
            return None

        symbol_definitions = getattr(self, "_symbol_definitions", {})
        target = symbol_definitions.get(reference_id) if isinstance(symbol_definitions, dict) else None
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


    def _convert_ellipse(self, *, element: etree._Element, coord_space: CoordinateSpace):
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

    def _convert_degenerate_shape_fallback(
        self,
        *,
        element: etree._Element,
        coord_space: CoordinateSpace,
    ):
        """Fallback for degenerate primitive shapes when resvg cannot convert."""
        tag = _local_name(element.tag).lower()
        epsilon = 1e-6

        if tag == "rect":
            width = _parse_float(element.get("width"))
            height = _parse_float(element.get("height"))
            if width is None or height is None:
                return None
            if width > DEFAULT_TOLERANCE and height > DEFAULT_TOLERANCE:
                return None
            x = _parse_float(element.get("x"), default=0.0) or 0.0
            y = _parse_float(element.get("y"), default=0.0) or 0.0
            if height > DEFAULT_TOLERANCE:
                segments = [LineSegment(Point(x, y), Point(x + epsilon, y + height))]
            elif width > DEFAULT_TOLERANCE:
                segments = [LineSegment(Point(x, y), Point(x + width, y + epsilon))]
            else:
                segments = [LineSegment(Point(x, y), Point(x + epsilon, y + epsilon))]
            return self._segments_to_path(element, segments, coord_space)

        if tag == "circle":
            radius = _parse_float(element.get("r"))
            if radius is None or radius > DEFAULT_TOLERANCE:
                return None
            cx = _parse_float(element.get("cx"), default=0.0) or 0.0
            cy = _parse_float(element.get("cy"), default=0.0) or 0.0
            segments = [LineSegment(Point(cx, cy), Point(cx + epsilon, cy + epsilon))]
            return self._segments_to_path(element, segments, coord_space)

        if tag == "ellipse":
            rx = _parse_float(element.get("rx"))
            ry = _parse_float(element.get("ry"))
            if rx is None or ry is None:
                return None
            if rx > DEFAULT_TOLERANCE and ry > DEFAULT_TOLERANCE:
                return None
            cx = _parse_float(element.get("cx"), default=0.0) or 0.0
            cy = _parse_float(element.get("cy"), default=0.0) or 0.0
            if ry > DEFAULT_TOLERANCE:
                segments = [LineSegment(Point(cx, cy - ry), Point(cx + epsilon, cy + ry))]
            elif rx > DEFAULT_TOLERANCE:
                segments = [LineSegment(Point(cx - rx, cy), Point(cx + rx, cy + epsilon))]
            else:
                segments = [LineSegment(Point(cx, cy), Point(cx + epsilon, cy + epsilon))]
            return self._segments_to_path(element, segments, coord_space)

        if tag == "line":
            x1 = _parse_float(element.get("x1"), default=0.0) or 0.0
            y1 = _parse_float(element.get("y1"), default=0.0) or 0.0
            x2 = _parse_float(element.get("x2"), default=0.0) or 0.0
            y2 = _parse_float(element.get("y2"), default=0.0) or 0.0
            if (
                abs(x2 - x1) > DEFAULT_TOLERANCE
                or abs(y2 - y1) > DEFAULT_TOLERANCE
            ):
                return None
            segments = [LineSegment(Point(x1, y1), Point(x2 + epsilon, y2 + epsilon))]
            return self._segments_to_path(element, segments, coord_space)

        return None

    def _convert_polygon(self, *, element: etree._Element, coord_space: CoordinateSpace):
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result
            self._trace_resvg_only_miss(element, "resvg_conversion_failed")
            return None
        self._trace_resvg_only_miss(element, self._resvg_miss_reason(element))
        return None

    def _convert_polyline(self, *, element: etree._Element, coord_space: CoordinateSpace):
        if self._can_use_resvg(element):
            resvg_result = self._convert_via_resvg(element, coord_space)
            if resvg_result is not None:
                return resvg_result
            self._trace_resvg_only_miss(element, "resvg_conversion_failed")
            return None
        self._trace_resvg_only_miss(element, self._resvg_miss_reason(element))
        return None

    def _segments_to_path(self, element: etree._Element, segments: list[SegmentType], coord_space: CoordinateSpace):
        style = styles_runtime.extract_style(self, element)
        clip_ref = self._resolve_clip_ref(element)
        mask_ref, mask_instance = self._resolve_mask_ref(element)
        policy = self._policy_options("geometry")
        allow_emf_fallback, allow_bitmap_fallback = self._geometry_fallback_flags(policy)
        segments, geom_meta, render_mode = apply_geometry_policy(list(segments), policy)
        bitmap_limits = self._bitmap_fallback_limits(policy)
        metadata = dict(style.metadata)
        self._attach_policy_metadata(metadata, "geometry")
        if geom_meta:
            policy_meta = metadata.setdefault("policy", {}).setdefault("geometry", {})
            policy_meta.update(geom_meta)

        if style.fill and not isinstance(style.fill, SolidPaint):
            if allow_bitmap_fallback:
                render_mode = FALLBACK_BITMAP
            elif allow_emf_fallback:
                render_mode = FALLBACK_EMF

        if render_mode == FALLBACK_EMF:
            emf_image = self._convert_path_to_emf(
                element=element,
                style=style,
                segments=segments,
                coord_space=coord_space,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
                metadata=metadata,
            )
            if emf_image is not None:
                self._trace_geometry_decision(element, "emf", emf_image.metadata if isinstance(emf_image.metadata, dict) else metadata)
                return emf_image
            self._logger.warning("Failed to build EMF fallback; reverting to native path.")
        elif render_mode == FALLBACK_BITMAP:
            if not allow_bitmap_fallback:
                self._logger.warning("Bitmap fallback disabled; falling back to native rendering.")
            else:
                bitmap_image = self._convert_path_to_bitmap(
                    element=element,
                    style=style,
                    segments=segments,
                    coord_space=coord_space,
                    clip_ref=clip_ref,
                    mask_ref=mask_ref,
                    mask_instance=mask_instance,
                    metadata=metadata,
                    bitmap_limits=bitmap_limits,
                )
                if bitmap_image is not None:
                    self._trace_geometry_decision(
                        element,
                        "bitmap",
                        bitmap_image.metadata if isinstance(bitmap_image.metadata, dict) else metadata,
                    )
                    return bitmap_image
                self._logger.warning("Failed to rasterize path; falling back to native rendering.")

        transformed = coord_space.apply_segments(segments)
        if not transformed:
            return None

        path_object = Path(
            segments=transformed,
            fill=style.fill,
            stroke=style.stroke,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=style.opacity,
            effects=style.effects,
            metadata=metadata,
        )
        self._apply_marker_metadata(element, path_object.metadata)
        self._trace_geometry_decision(element, "native", path_object.metadata)
        marker_shapes = self._build_marker_shapes(element, path_object)
        if marker_shapes:
            return [path_object, *marker_shapes]
        return path_object

    def _resvg_segments_to_path(
        self,
        *,
        element: etree._Element,
        segments: list[SegmentType],
        coord_space: CoordinateSpace,
        style: StyleResult,
        metadata: dict[str, Any],
        clip_ref: ClipRef | None,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
    ):
        policy = self._policy_options("geometry")
        allow_emf_fallback, allow_bitmap_fallback = self._geometry_fallback_flags(policy)
        segments, geom_meta, render_mode = apply_geometry_policy(list(segments), policy)
        bitmap_limits = self._bitmap_fallback_limits(policy)
        if geom_meta:
            policy_meta = metadata.setdefault("policy", {}).setdefault("geometry", {})
            policy_meta.update(geom_meta)

        if style.fill and not isinstance(style.fill, SolidPaint):
            if allow_bitmap_fallback:
                render_mode = FALLBACK_BITMAP
            elif allow_emf_fallback:
                render_mode = FALLBACK_EMF

        fallback_to_bitmap = False
        if render_mode == FALLBACK_EMF:
            emf_image = self._convert_path_to_emf(
                element=element,
                style=style,
                segments=segments,
                coord_space=coord_space,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
                metadata=metadata,
            )
            if emf_image is not None:
                self._process_mask_metadata(emf_image)
                self._trace_geometry_decision(
                    element,
                    "emf",
                    emf_image.metadata if isinstance(emf_image.metadata, dict) else metadata,
                )
                return emf_image
            if allow_bitmap_fallback:
                self._logger.warning("Failed to build EMF fallback; attempting bitmap fallback.")
                fallback_to_bitmap = True
            else:
                self._logger.warning("Failed to build EMF fallback; bitmap fallback disabled.")

        if (render_mode == FALLBACK_BITMAP or fallback_to_bitmap) and allow_bitmap_fallback:
            bitmap_image = self._convert_path_to_bitmap(
                element=element,
                style=style,
                segments=segments,
                coord_space=coord_space,
                clip_ref=clip_ref,
                mask_ref=mask_ref,
                mask_instance=mask_instance,
                metadata=metadata,
                bitmap_limits=bitmap_limits,
            )
            if bitmap_image is not None:
                if fallback_to_bitmap:
                    geometry_policy = metadata.setdefault("policy", {}).setdefault("geometry", {})
                    geometry_policy["render_mode"] = FALLBACK_BITMAP
                self._process_mask_metadata(bitmap_image)
                self._trace_geometry_decision(
                    element,
                    "bitmap",
                    bitmap_image.metadata if isinstance(bitmap_image.metadata, dict) else metadata,
                )
                return bitmap_image
            self._logger.warning("Failed to rasterize path; falling back to native rendering.")
        elif render_mode == FALLBACK_BITMAP and not allow_bitmap_fallback:
            self._logger.warning("Bitmap fallback disabled; falling back to native rendering.")

        transformed = coord_space.apply_segments(segments)
        if not transformed:
            return None

        path_object = Path(
            segments=transformed,
            fill=style.fill,
            stroke=style.stroke,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=style.opacity,
            effects=style.effects,
            metadata=metadata,
        )
        self._process_mask_metadata(path_object)
        self._apply_marker_metadata(element, path_object.metadata)
        self._trace_geometry_decision(element, "resvg", path_object.metadata)
        marker_shapes = self._build_marker_shapes(element, path_object)
        if marker_shapes:
            return [path_object, *marker_shapes]
        return path_object

    def _convert_image(self, *, element: etree._Element, coord_space: CoordinateSpace):
        href = element.get("href") or element.get("{http://www.w3.org/1999/xlink}href")
        href = self._normalize_image_href(href)
        if not href:
            return None
        width = _parse_float(element.get("width"))
        height = _parse_float(element.get("height"))
        if width is None or height is None or width <= 0 or height <= 0:
            return None
        x = _parse_float(element.get("x"), default=0.0) or 0.0
        y = _parse_float(element.get("y"), default=0.0) or 0.0

        rect_points = [
            (x, y),
            (x + width, y),
            (x + width, y + height),
            (x, y + height),
        ]
        transformed_points = [coord_space.apply_point(px, py) for (px, py) in rect_points]
        bbox = _compute_bbox(transformed_points)

        image_policy = self._policy_options("image")
        style = styles_runtime.extract_style(self, element)

        image_service = self._services.image_service
        resource: ImageResource | None = None
        if href and image_service:
            resource = image_service.resolve(href)
        if resource is None and href:
            resource = ImageService._data_uri_resolver(href)
        if resource is None and href:
            resource = self._resolve_image_from_source_path(href)

        color_service = getattr(self._services, "color_space_service", None)
        color_result = None
        if resource and color_service and image_policy:
            normalization = image_policy.get("colorspace_normalization", "rgb")
            color_result = color_service.normalize_resource(resource, normalization=normalization)
            resource = color_result.resource

        format_hint = _guess_image_format(
            href,
            resource.data if resource else None,
            resource.mime_type if resource else None,
        )
        clip_ref = self._resolve_clip_ref(element)
        mask_ref, mask_instance = self._resolve_mask_ref(element)
        metadata: dict[str, Any] = dict(style.metadata)
        if resource and resource.source:
            metadata["image_source"] = resource.source
        if href:
            metadata["href"] = href
        self._attach_policy_metadata(metadata, "image")
        if image_policy:
            self._attach_policy_metadata(metadata, "image", extra=image_policy)
        if color_result:
            policy_meta = metadata.setdefault("policy", {}).setdefault("image", {})
            if color_result.result.converted:
                policy_meta["colorspace_mode"] = color_result.result.mode
                if color_result.result.warnings:
                    policy_meta["colorspace_warnings"] = list(color_result.result.warnings)
            if color_result.result.metadata:
                policy_meta.setdefault("colorspace_metadata", color_result.result.metadata)

        image = Image(
            origin=Point(bbox.x, bbox.y),
            size=bbox,
            data=resource.data if resource else None,
            format=format_hint,
            href=href,
            clip=clip_ref,
            mask=mask_ref,
            mask_instance=mask_instance,
            opacity=style.opacity,
            transform=None,
            metadata=metadata,
        )
        self._process_mask_metadata(image)
        self._trace_geometry_decision(element, "native", image.metadata)
        self._trace_stage(
            "image_embedded",
            stage="image",
            metadata={
                "format": format_hint,
                "embedded_data": bool(resource and resource.data),
                "href": href if href else None,
            },
            subject=element.get("id"),
        )
        return image

    @staticmethod
    def _normalize_image_href(href: str | None) -> str | None:
        if href is None:
            return None
        token = href.strip()
        if token.lower().startswith("url(") and token.endswith(")"):
            token = token[4:-1].strip()
            if (token.startswith("'") and token.endswith("'")) or (token.startswith('"') and token.endswith('"')):
                token = token[1:-1]
        return token or None

    def _resolve_image_from_source_path(self, href: str) -> ImageResource | None:
        token = href.strip().lower()
        if token.startswith(("http://", "https://", "ftp://", "#")):
            return None
        source_path = None
        if hasattr(self._services, "resolve"):
            source_path = self._services.resolve("source_path")
        if not isinstance(source_path, str) or not source_path:
            return None
        try:
            base_dir = FsPath(source_path).expanduser().resolve().parent
            target = FsPath(href).expanduser()
            if not target.is_absolute():
                target = (base_dir / target).resolve()
            else:
                target = target.resolve()
            if not target.is_file():
                return None
            return ImageResource(data=target.read_bytes(), source="file")
        except Exception:
            return None

    def _convert_foreign_object(
        self,
        *,
        element: etree._Element,
        coord_space: CoordinateSpace,
        traverse_callback: Callable[[etree._Element, Any | None], list],
        current_navigation,
    ):
        width = _parse_float(element.get("width"))
        height = _parse_float(element.get("height"))
        if width is None or height is None or width <= 0 or height <= 0:
            return None
        x = _parse_float(element.get("x"), default=0.0) or 0.0
        y = _parse_float(element.get("y"), default=0.0) or 0.0

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
            placeholder = self._foreign_object_placeholder(bbox, clip_ref, mask_ref, mask_instance, metadata)
            placeholder = replace(placeholder, opacity=style.opacity)
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
                metadata=metadata
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
                placeholder = self._foreign_object_placeholder(bbox, clip_ref, mask_ref, mask_instance, metadata)
                return replace(placeholder, opacity=style.opacity)

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
                placeholder = self._foreign_object_placeholder(bbox, clip_ref, mask_ref, mask_instance, metadata)
                placeholder = replace(placeholder, opacity=style.opacity)
                self._trace_geometry_decision(element, "placeholder", placeholder.metadata)
                self._trace_stage(
                    "foreign_object_placeholder",
                    stage="foreign_object",
                    metadata=metadata.get("foreign_object"),
                    subject=element.get("id"),
                )
                return placeholder
            run = Run(text=text_content, font_family="Arial", font_size_pt=12.0)
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

        placeholder = self._foreign_object_placeholder(bbox, clip_ref, mask_ref, mask_instance, metadata)
        placeholder = replace(placeholder, opacity=style.opacity)
        self._trace_geometry_decision(element, "placeholder", placeholder.metadata)
        self._trace_stage(
            "foreign_object_placeholder",
            stage="foreign_object",
            metadata=metadata.get("foreign_object"),
            subject=element.get("id"),
        )
        return placeholder

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
