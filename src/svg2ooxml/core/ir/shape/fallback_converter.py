"""Segments-to-path and degenerate shape fallback methods."""

from __future__ import annotations

from lxml import etree

from svg2ooxml.core.ir.shape_converters_utils import (
    _local_name,
)
from svg2ooxml.core.styling import style_runtime as styles_runtime
from svg2ooxml.core.styling.stroke_width_policy import (
    apply_transform_stroke_width_policy,
)
from svg2ooxml.core.traversal.constants import DEFAULT_TOLERANCE
from svg2ooxml.ir.geometry import LineSegment, Point, SegmentType
from svg2ooxml.ir.scene import Path
from svg2ooxml.policy.constants import FALLBACK_BITMAP, FALLBACK_EMF
from svg2ooxml.policy.geometry import apply_geometry_policy


class ShapeFallbackPathMixin:
    """Mixin housing _segments_to_path and degenerate shape fallback."""

    def _segments_to_path(
        self,
        element: etree._Element,
        segments: list[SegmentType],
        coord_space,
    ):
        style = styles_runtime.extract_style(self, element)
        clip_ref = self._resolve_clip_ref(
            element,
            use_transform=coord_space.current,
        )
        mask_ref, mask_instance = self._resolve_mask_ref(element)
        policy = self._policy_options("geometry")
        allow_emf_fallback, allow_bitmap_fallback = self._geometry_fallback_flags(
            policy
        )
        segments, geom_meta, render_mode = apply_geometry_policy(list(segments), policy)
        bitmap_limits = self._bitmap_fallback_limits(policy)
        metadata = dict(style.metadata)
        self._attach_policy_metadata(metadata, "geometry")
        style = apply_transform_stroke_width_policy(
            style,
            element=element,
            matrix=coord_space.current,
            metadata=metadata,
        )
        if geom_meta:
            policy_meta = metadata.setdefault("policy", {}).setdefault("geometry", {})
            policy_meta.update(geom_meta)

        pattern_fallback = None
        if self._pattern_fill_requires_path_fallback(style.fill):
            pattern_fallback = self._prefer_pattern_path_fallback(
                metadata,
                allow_emf_fallback=allow_emf_fallback,
                allow_bitmap_fallback=allow_bitmap_fallback,
            )

        if pattern_fallback is not None:
            render_mode = pattern_fallback
        elif style.fill and not self._fill_can_render_natively(style.fill, metadata):
            fill_fallback = self._prefer_non_native_fill_fallback(
                style.fill,
                allow_emf_fallback=allow_emf_fallback,
                allow_bitmap_fallback=allow_bitmap_fallback,
            )
            if fill_fallback is not None:
                render_mode = fill_fallback

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
                self._trace_geometry_decision(
                    element,
                    "emf",
                    (
                        emf_image.metadata
                        if isinstance(emf_image.metadata, dict)
                        else metadata
                    ),
                )
                return emf_image
            self._logger.warning(
                "Failed to build EMF fallback; reverting to native path."
            )
        elif render_mode == FALLBACK_BITMAP:
            if not allow_bitmap_fallback:
                self._logger.warning(
                    "Bitmap fallback disabled; falling back to native rendering."
                )
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
                        (
                            bitmap_image.metadata
                            if isinstance(bitmap_image.metadata, dict)
                            else metadata
                        ),
                    )
                    return bitmap_image
                self._logger.warning(
                    "Failed to rasterize path; falling back to native rendering."
                )

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

    def _convert_degenerate_shape_fallback(
        self,
        *,
        element: etree._Element,
        coord_space,
    ):
        """Fallback for degenerate primitive shapes when resvg cannot convert."""
        tag = _local_name(element.tag).lower()
        epsilon = 1e-6
        context = getattr(self, "_conversion_context", None)

        if tag == "rect":
            width = self._resolve_length(element.get("width"), context, axis="x")
            height = self._resolve_length(element.get("height"), context, axis="y")
            if width is None or height is None:
                return None
            if width > DEFAULT_TOLERANCE and height > DEFAULT_TOLERANCE:
                return None
            x = self._resolve_length(element.get("x"), context, axis="x")
            y = self._resolve_length(element.get("y"), context, axis="y")
            if height > DEFAULT_TOLERANCE:
                segments = [LineSegment(Point(x, y), Point(x + epsilon, y + height))]
            elif width > DEFAULT_TOLERANCE:
                segments = [LineSegment(Point(x, y), Point(x + width, y + epsilon))]
            else:
                segments = [LineSegment(Point(x, y), Point(x + epsilon, y + epsilon))]
            return self._segments_to_path(element, segments, coord_space)

        if tag == "circle":
            radius = self._resolve_length(element.get("r"), context, axis="x")
            if radius is None or radius > DEFAULT_TOLERANCE:
                return None
            cx = self._resolve_length(element.get("cx"), context, axis="x")
            cy = self._resolve_length(element.get("cy"), context, axis="y")
            segments = [LineSegment(Point(cx, cy), Point(cx + epsilon, cy + epsilon))]
            return self._segments_to_path(element, segments, coord_space)

        if tag == "ellipse":
            rx = self._resolve_length(element.get("rx"), context, axis="x")
            ry = self._resolve_length(element.get("ry"), context, axis="y")
            if rx is None or ry is None:
                return None
            if rx > DEFAULT_TOLERANCE and ry > DEFAULT_TOLERANCE:
                return None
            cx = self._resolve_length(element.get("cx"), context, axis="x")
            cy = self._resolve_length(element.get("cy"), context, axis="y")
            if ry > DEFAULT_TOLERANCE:
                segments = [
                    LineSegment(Point(cx, cy - ry), Point(cx + epsilon, cy + ry))
                ]
            elif rx > DEFAULT_TOLERANCE:
                segments = [
                    LineSegment(Point(cx - rx, cy), Point(cx + rx, cy + epsilon))
                ]
            else:
                segments = [
                    LineSegment(Point(cx, cy), Point(cx + epsilon, cy + epsilon))
                ]
            return self._segments_to_path(element, segments, coord_space)

        if tag == "line":
            x1 = self._resolve_length(element.get("x1"), context, axis="x")
            y1 = self._resolve_length(element.get("y1"), context, axis="y")
            x2 = self._resolve_length(element.get("x2"), context, axis="x")
            y2 = self._resolve_length(element.get("y2"), context, axis="y")
            if abs(x2 - x1) > DEFAULT_TOLERANCE or abs(y2 - y1) > DEFAULT_TOLERANCE:
                return None
            segments = [LineSegment(Point(x1, y1), Point(x2 + epsilon, y2 + epsilon))]
            return self._segments_to_path(element, segments, coord_space)

        return None
