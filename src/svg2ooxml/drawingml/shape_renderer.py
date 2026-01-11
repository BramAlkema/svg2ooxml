"""Shape rendering helpers extracted from DrawingMLWriter."""

from __future__ import annotations

import logging
from typing import Callable

from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.scene import Group, Image, Path as IRPath
from svg2ooxml.ir.shapes import Circle, Ellipse, Rectangle, Line, Polygon, Polyline
from svg2ooxml.policy.constants import FALLBACK_BITMAP, FALLBACK_RASTERIZE

from . import paint_runtime, shapes_runtime
from .animation_pipeline import AnimationPipeline
from .generator import DrawingMLPathGenerator
from .image import render_picture
from .rasterizer import Rasterizer


class DrawingMLShapeRenderer:
    """Render shapes, paths, and images into DrawingML fragments."""

    def __init__(
        self,
        *,
        rectangle_template: str,
        preset_template: str,
        path_template: str,
        line_template: str,
        picture_template: str,
        path_generator: DrawingMLPathGenerator,
        policy_for: Callable[[dict[str, object] | None, str], dict[str, object]],
        register_media: Callable[[Image], str],
        trace_writer: Callable[..., None],
        animation_pipeline: AnimationPipeline,
        rasterizer: Rasterizer | None,
        logger: logging.Logger,
    ) -> None:
        self._rectangle_template = rectangle_template
        self._preset_template = preset_template
        self._path_template = path_template
        self._line_template = line_template
        self._picture_template = picture_template
        self._path_generator = path_generator
        self._policy_for = policy_for
        self._register_media = register_media
        self._trace_writer = trace_writer
        self._animation_pipeline = animation_pipeline
        self._rasterizer = rasterizer
        self._logger = logger

    def render(
        self,
        element,
        shape_id: int,
        metadata: dict[str, object],
        *,
        hyperlink_xml: str,
        clip_path_xml: str,
        mask_xml: str,
    ) -> tuple[str, int] | None:
        if isinstance(element, Rectangle):
            rasterized = self._maybe_rasterize(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_path_xml,
                mask_xml=mask_xml,
            )
            if rasterized is not None:
                return rasterized
            xml = shapes_runtime.render_rectangle(
                element,
                shape_id,
                template=self._rectangle_template,
                paint_to_fill=paint_runtime.paint_to_fill,
                stroke_to_xml=paint_runtime.stroke_to_xml,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_path_xml,
                mask_xml=mask_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, Circle):
            rasterized = self._maybe_rasterize(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_path_xml,
                mask_xml=mask_xml,
            )
            if rasterized is not None:
                return rasterized
            xml = shapes_runtime.render_circle(
                element,
                shape_id,
                template=self._preset_template,
                paint_to_fill=paint_runtime.paint_to_fill,
                stroke_to_xml=paint_runtime.stroke_to_xml,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_path_xml,
                mask_xml=mask_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, Ellipse):
            rasterized = self._maybe_rasterize(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_path_xml,
                mask_xml=mask_xml,
            )
            if rasterized is not None:
                return rasterized
            xml = shapes_runtime.render_ellipse(
                element,
                shape_id,
                template=self._preset_template,
                paint_to_fill=paint_runtime.paint_to_fill,
                stroke_to_xml=paint_runtime.stroke_to_xml,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_path_xml,
                mask_xml=mask_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, Line):
            xml = shapes_runtime.render_line(
                element,
                shape_id,
                template=self._line_template,
                path_generator=self._path_generator,
                stroke_to_xml=paint_runtime.stroke_to_xml,
                paint_to_fill=paint_runtime.paint_to_fill,
                policy_for=self._policy_for,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_path_xml,
                mask_xml=mask_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, Polyline):
            xml = shapes_runtime.render_polyline(
                element,
                shape_id,
                template=self._path_template,
                path_generator=self._path_generator,
                paint_to_fill=paint_runtime.paint_to_fill,
                stroke_to_xml=paint_runtime.stroke_to_xml,
                policy_for=self._policy_for,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_path_xml,
                mask_xml=mask_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, Polygon):
            xml = shapes_runtime.render_polygon(
                element,
                shape_id,
                template=self._path_template,
                path_generator=self._path_generator,
                paint_to_fill=paint_runtime.paint_to_fill,
                stroke_to_xml=paint_runtime.stroke_to_xml,
                policy_for=self._policy_for,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_path_xml,
                mask_xml=mask_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, IRPath):
            rasterized = self._maybe_rasterize(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_path_xml,
                mask_xml=mask_xml,
            )
            if rasterized is not None:
                return rasterized
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
                clip_path_xml=clip_path_xml,
                mask_xml=mask_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, Image):
            if element.data is None and element.href is None:
                self._logger.warning("Image element missing data and href; skipping image")
                return None
            if element.data is None:
                self._logger.warning("External image references not yet supported; skipping image")
                return None
            rendered = render_picture(
                element,
                shape_id,
                template=self._picture_template,
                policy_for=self._policy_for,
                register_media=self._register_media,
                hyperlink_xml=hyperlink_xml,
                clip_path_xml=clip_path_xml,
                mask_xml=mask_xml,
            )
            if rendered is None:
                return None
            return rendered, shape_id + 1
        if isinstance(element, Group):
            return None
        return None

    def _maybe_rasterize(
        self,
        element,
        shape_id: int,
        metadata: dict[str, object],
        *,
        hyperlink_xml: str,
        clip_path_xml: str,
        mask_xml: str,
    ) -> tuple[str, int] | None:
        if self._rasterizer is None:
            return None
        policy = metadata.setdefault("policy", {}) if isinstance(metadata, dict) else {}
        geometry_policy = policy.setdefault("geometry", {})
        fallback = geometry_policy.get("suggest_fallback")
        if fallback not in {FALLBACK_BITMAP, FALLBACK_RASTERIZE}:
            return None
        try:
            result = self._rasterizer.rasterize(element)
        except Exception:  # pragma: no cover - defensive
            self._logger.debug("Rasterization failed for %s", type(element).__name__, exc_info=True)
            return None
        if result is None:
            return None

        origin = Point(result.bounds.x, result.bounds.y)
        size_rect = Rect(0.0, 0.0, result.bounds.width, result.bounds.height)
        image_metadata = {
            "rasterized": True,
            "source_shape": type(element).__name__,
        }
        element_ids = metadata.get("element_ids") if isinstance(metadata, dict) else None
        if isinstance(element_ids, list):
            image_metadata["element_ids"] = list(element_ids)
            self._animation_pipeline.register_element_ids(element_ids, shape_id)
        raster_image = Image(
            origin=origin,
            size=size_rect,
            data=result.data,
            format="png",
            metadata=image_metadata,
        )
        xml = render_picture(
            raster_image,
            shape_id,
            template=self._picture_template,
            policy_for=self._policy_for,
            register_media=self._register_media,
            hyperlink_xml=hyperlink_xml,
            clip_path_xml=clip_path_xml,
            mask_xml=mask_xml,
        )
        if xml is None:
            return None
        geometry_policy.setdefault("rasterized_media", []).append({"shape_id": shape_id, "format": "png"})
        self._trace_writer(
            "geometry_rasterized",
            stage="media",
            metadata={
                "shape_id": shape_id,
                "format": "png",
                "source_shape": type(element).__name__,
            },
        )
        return xml, shape_id + 1


__all__ = ["DrawingMLShapeRenderer"]
