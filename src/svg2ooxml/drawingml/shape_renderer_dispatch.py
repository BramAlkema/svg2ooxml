"""Shape dispatch for :class:`DrawingMLShapeRenderer`."""

from __future__ import annotations

from svg2ooxml.ir.scene import Group, Image
from svg2ooxml.ir.scene import Path as IRPath
from svg2ooxml.ir.shapes import Circle, Ellipse, Line, Polygon, Polyline, Rectangle

from . import paint_runtime, shapes_runtime
from .filter_fallback import render_shape_filter_fallback
from .image import render_picture
from .shape_renderer_utils import (
    apply_clip_bounds,
    has_fill_and_stroke,
    is_stroke_first,
)


class ShapeRendererDispatchMixin:
    """Dispatch IR elements to DrawingML shape, path, picture, or raster output."""

    def render(
        self,
        element,
        shape_id: int,
        metadata: dict[str, object],
        *,
        hyperlink_xml: str,
    ) -> tuple[str, int] | None:
        element = self._prepare_element(
            element,
            shape_id,
            metadata,
            hyperlink_xml=hyperlink_xml,
        )
        if element is None:
            return None
        if isinstance(element, tuple):
            return element

        if is_stroke_first(metadata) and has_fill_and_stroke(element):
            return self._render_reversed_paint_order(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
            )

        if isinstance(element, Rectangle):
            return self._render_rectangle(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
            )
        if isinstance(element, Circle):
            return self._render_circle(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
            )
        if isinstance(element, Ellipse):
            return self._render_ellipse(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
            )
        if isinstance(element, Line):
            return self._render_line(element, shape_id, metadata, hyperlink_xml=hyperlink_xml)
        if isinstance(element, Polyline):
            return self._render_polyline(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
            )
        if isinstance(element, Polygon):
            return self._render_polygon(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
            )
        if isinstance(element, IRPath):
            return self._render_path(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
            )
        if isinstance(element, Image):
            return self._render_image(element, shape_id, hyperlink_xml=hyperlink_xml)
        if isinstance(element, Group):
            return None
        return None

    def _prepare_element(
        self,
        element,
        shape_id: int,
        metadata: dict[str, object],
        *,
        hyperlink_xml: str,
    ):
        element = self._register_pattern_tile(element)
        filter_fallback = render_shape_filter_fallback(
            element,
            shape_id,
            metadata,
            picture_template=self._picture_template,
            policy_for=self._policy_for,
            register_media=self._register_media,
            trace_writer=self._trace_writer,
            hyperlink_xml=hyperlink_xml,
        )
        if filter_fallback is not None:
            return filter_fallback

        element = self._strip_invalid_filter_effects(element)
        element = apply_clip_bounds(element, metadata)
        if self._rasterizer is None and self._needs_gradient_raster(element):
            element = self._apply_gradient_fallback(element, metadata)

        if metadata.get("mix_blend_mode") and self._rasterizer is not None:
            rasterized = self._maybe_rasterize(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
            )
            if rasterized is not None:
                return rasterized
        return element

    def _render_rectangle(
        self,
        element: Rectangle,
        shape_id: int,
        metadata: dict[str, object],
        *,
        hyperlink_xml: str,
    ) -> tuple[str, int] | None:
        rasterized = self._maybe_rasterize(
            element,
            shape_id,
            metadata,
            hyperlink_xml=hyperlink_xml,
        )
        if rasterized is not None:
            return rasterized
        self._register_animation_ids(metadata, shape_id)
        xml = shapes_runtime.render_rectangle(
            element,
            shape_id,
            template=self._rectangle_template,
            paint_to_fill=paint_runtime.paint_to_fill,
            stroke_to_xml=paint_runtime.stroke_to_xml,
            hyperlink_xml=hyperlink_xml,
        )
        return xml, shape_id + 1

    def _render_circle(
        self,
        element: Circle,
        shape_id: int,
        metadata: dict[str, object],
        *,
        hyperlink_xml: str,
    ) -> tuple[str, int] | None:
        rasterized = self._maybe_rasterize(
            element,
            shape_id,
            metadata,
            hyperlink_xml=hyperlink_xml,
        )
        if rasterized is not None:
            return rasterized
        self._register_animation_ids(metadata, shape_id)
        xml = shapes_runtime.render_circle(
            element,
            shape_id,
            template=self._preset_template,
            paint_to_fill=paint_runtime.paint_to_fill,
            stroke_to_xml=paint_runtime.stroke_to_xml,
            hyperlink_xml=hyperlink_xml,
        )
        return xml, shape_id + 1

    def _render_ellipse(
        self,
        element: Ellipse,
        shape_id: int,
        metadata: dict[str, object],
        *,
        hyperlink_xml: str,
    ) -> tuple[str, int] | None:
        rasterized = self._maybe_rasterize(
            element,
            shape_id,
            metadata,
            hyperlink_xml=hyperlink_xml,
        )
        if rasterized is not None:
            return rasterized
        self._register_animation_ids(metadata, shape_id)
        xml = shapes_runtime.render_ellipse(
            element,
            shape_id,
            template=self._preset_template,
            paint_to_fill=paint_runtime.paint_to_fill,
            stroke_to_xml=paint_runtime.stroke_to_xml,
            hyperlink_xml=hyperlink_xml,
        )
        return xml, shape_id + 1

    def _render_line(
        self,
        element: Line,
        shape_id: int,
        metadata: dict[str, object],
        *,
        hyperlink_xml: str,
    ) -> tuple[str, int] | None:
        self._register_animation_ids(metadata, shape_id)
        xml = shapes_runtime.render_line(
            element,
            shape_id,
            template=self._line_template,
            path_generator=self._path_generator,
            stroke_to_xml=paint_runtime.stroke_to_xml,
            paint_to_fill=paint_runtime.paint_to_fill,
            policy_for=self._policy_for,
            hyperlink_xml=hyperlink_xml,
        )
        return xml, shape_id + 1

    def _render_polyline(
        self,
        element: Polyline,
        shape_id: int,
        metadata: dict[str, object],
        *,
        hyperlink_xml: str,
    ) -> tuple[str, int] | None:
        self._register_animation_ids(metadata, shape_id)
        xml = shapes_runtime.render_polyline(
            element,
            shape_id,
            template=self._path_template,
            path_generator=self._path_generator,
            paint_to_fill=paint_runtime.paint_to_fill,
            stroke_to_xml=paint_runtime.stroke_to_xml,
            policy_for=self._policy_for,
            hyperlink_xml=hyperlink_xml,
        )
        return xml, shape_id + 1

    def _render_polygon(
        self,
        element: Polygon,
        shape_id: int,
        metadata: dict[str, object],
        *,
        hyperlink_xml: str,
    ) -> tuple[str, int] | None:
        self._register_animation_ids(metadata, shape_id)
        xml = shapes_runtime.render_polygon(
            element,
            shape_id,
            template=self._path_template,
            path_generator=self._path_generator,
            paint_to_fill=paint_runtime.paint_to_fill,
            stroke_to_xml=paint_runtime.stroke_to_xml,
            policy_for=self._policy_for,
            hyperlink_xml=hyperlink_xml,
        )
        return xml, shape_id + 1

    def _render_path(
        self,
        element: IRPath,
        shape_id: int,
        metadata: dict[str, object],
        *,
        hyperlink_xml: str,
    ) -> tuple[str, int] | None:
        rasterized = self._maybe_rasterize(
            element,
            shape_id,
            metadata,
            hyperlink_xml=hyperlink_xml,
        )
        if rasterized is not None:
            return rasterized
        self._register_animation_ids(metadata, shape_id)
        xml = shapes_runtime.render_path(
            element,
            shape_id,
            template=self._path_template,
            paint_to_fill=paint_runtime.paint_to_fill,
            stroke_to_xml=paint_runtime.stroke_to_xml,
            path_generator=self._path_generator,
            policy_for=self._policy_for,
            logger=self._logger,
            hyperlink_xml=hyperlink_xml,
        )
        overlay = self._maybe_clip_overlay(element, shape_id + 1)
        if overlay:
            return xml + "\n" + overlay, shape_id + 2
        return xml, shape_id + 1

    def _render_image(
        self,
        element: Image,
        shape_id: int,
        *,
        hyperlink_xml: str,
    ) -> tuple[str, int] | None:
        if element.data is None and element.href is None:
            self._logger.warning("Image element missing data and href; skipping image")
            return None
        clip_geometry = ""
        clip = getattr(element, "clip", None)
        if clip is not None and getattr(clip, "custom_geometry_xml", None):
            clip_geometry = clip.custom_geometry_xml
        rendered = render_picture(
            element,
            shape_id,
            template=self._picture_template,
            policy_for=self._policy_for,
            register_media=self._register_media,
            hyperlink_xml=hyperlink_xml,
            geometry_xml=clip_geometry,
        )
        if rendered is None:
            return None
        return rendered, shape_id + 1

    def _register_animation_ids(
        self,
        metadata: dict[str, object],
        shape_id: int,
    ) -> None:
        element_ids = metadata.get("element_ids")
        if isinstance(element_ids, list):
            self._animation_pipeline.register_element_ids(element_ids, shape_id)


__all__ = ["ShapeRendererDispatchMixin"]
