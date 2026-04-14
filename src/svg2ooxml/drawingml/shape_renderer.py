"""Shape rendering helpers extracted from DrawingMLWriter."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace

from svg2ooxml.ir.effects import CustomEffect
from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.paint import PatternPaint, RadialGradientPaint, SolidPaint
from svg2ooxml.ir.scene import Group, Image
from svg2ooxml.ir.scene import Path as IRPath
from svg2ooxml.ir.shapes import Circle, Ellipse, Line, Polygon, Polyline, Rectangle
from svg2ooxml.policy.constants import FALLBACK_BITMAP, FALLBACK_RASTERIZE

from . import paint_runtime, shapes_runtime
from .animation_pipeline import AnimationPipeline
from .filter_fallback import resolve_filter_fallback_bounds
from .generator import DrawingMLPathGenerator
from .image import render_picture
from .rasterizer import Rasterizer


def _is_stroke_first(metadata: dict[str, object]) -> bool:
    """Return True when paint-order puts stroke before fill."""
    po = metadata.get("paint_order")
    if not isinstance(po, str):
        return False
    tokens = po.lower().split()
    try:
        si = tokens.index("stroke")
        fi = tokens.index("fill")
        return si < fi
    except ValueError:
        # "stroke" alone means "stroke fill markers"
        return tokens[0] == "stroke" if tokens else False


def _has_fill_and_stroke(element) -> bool:
    return getattr(element, "fill", None) is not None and getattr(element, "stroke", None) is not None


class DrawingMLShapeRenderer:
    """Render shapes, paths, and images into DrawingML fragments."""

    _INVALID_EFFECT_SUBSTRINGS = (
        "svg2ooxml:sourcegraphic",
        "svg2ooxml:sourcealpha",
        "svg2ooxml:emf",
        "svg2ooxml:raster",
    )

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
    ) -> tuple[str, int] | None:
        # Register pattern tile media before rendering
        element = self._register_pattern_tile(element)

        filter_fallback = self._maybe_filter_fallback(
            element,
            shape_id,
            metadata,
            hyperlink_xml=hyperlink_xml,
        )
        if filter_fallback is not None:
            return filter_fallback
        element = self._strip_invalid_filter_effects(element)

        # Apply clip bounds approximation (xfrm intersection).
        element = _apply_clip_bounds(element, metadata)

        # mix-blend-mode: rasterize to PNG since DrawingML has no blend modes.
        if metadata.get("mix_blend_mode") and self._rasterizer is not None:
            rasterized = self._maybe_rasterize(
                element, shape_id, metadata, hyperlink_xml=hyperlink_xml,
            )
            if rasterized is not None:
                return rasterized

        # Paint-order reversal: when "stroke" comes before "fill", emit
        # a stroke-only shape behind a fill-only shape.
        if _is_stroke_first(metadata) and _has_fill_and_stroke(element):
            return self._render_reversed_paint_order(
                element, shape_id, metadata, hyperlink_xml=hyperlink_xml,
            )

        if isinstance(element, Rectangle):
            rasterized = self._maybe_rasterize(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
            )
            if rasterized is not None:
                return rasterized

            # Register for animations
            element_ids = metadata.get("element_ids")
            if isinstance(element_ids, list):
                self._animation_pipeline.register_element_ids(element_ids, shape_id)

            xml = shapes_runtime.render_rectangle(
                element,
                shape_id,
                template=self._rectangle_template,
                paint_to_fill=paint_runtime.paint_to_fill,
                stroke_to_xml=paint_runtime.stroke_to_xml,
                hyperlink_xml=hyperlink_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, Circle):
            rasterized = self._maybe_rasterize(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
            )
            if rasterized is not None:
                return rasterized

            # Register for animations
            element_ids = metadata.get("element_ids")
            if isinstance(element_ids, list):
                self._animation_pipeline.register_element_ids(element_ids, shape_id)

            xml = shapes_runtime.render_circle(
                element,
                shape_id,
                template=self._preset_template,
                paint_to_fill=paint_runtime.paint_to_fill,
                stroke_to_xml=paint_runtime.stroke_to_xml,
                hyperlink_xml=hyperlink_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, Ellipse):
            rasterized = self._maybe_rasterize(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
            )
            if rasterized is not None:
                return rasterized

            # Register for animations
            element_ids = metadata.get("element_ids")
            if isinstance(element_ids, list):
                self._animation_pipeline.register_element_ids(element_ids, shape_id)

            xml = shapes_runtime.render_ellipse(
                element,
                shape_id,
                template=self._preset_template,
                paint_to_fill=paint_runtime.paint_to_fill,
                stroke_to_xml=paint_runtime.stroke_to_xml,
                hyperlink_xml=hyperlink_xml,
            )
            return xml, shape_id + 1
        if isinstance(element, Line):
            # Register for animations
            element_ids = metadata.get("element_ids")
            if isinstance(element_ids, list):
                self._animation_pipeline.register_element_ids(element_ids, shape_id)

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
        if isinstance(element, Polyline):
            # Register for animations
            element_ids = metadata.get("element_ids")
            if isinstance(element_ids, list):
                self._animation_pipeline.register_element_ids(element_ids, shape_id)

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
        if isinstance(element, Polygon):
            # Register for animations
            element_ids = metadata.get("element_ids")
            if isinstance(element_ids, list):
                self._animation_pipeline.register_element_ids(element_ids, shape_id)

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
        if isinstance(element, IRPath):
            rasterized = self._maybe_rasterize(
                element,
                shape_id,
                metadata,
                hyperlink_xml=hyperlink_xml,
            )
            if rasterized is not None:
                return rasterized

            # Register for animations
            element_ids = metadata.get("element_ids")
            if isinstance(element_ids, list):
                self._animation_pipeline.register_element_ids(element_ids, shape_id)

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
            # Clip overlay — white EMF frame with even-odd cutout.
            overlay = self._maybe_clip_overlay(element, shape_id + 1)
            if overlay:
                return xml + "\n" + overlay, shape_id + 2
            return xml, shape_id + 1
        if isinstance(element, Image):
            if element.data is None and element.href is None:
                self._logger.warning("Image element missing data and href; skipping image")
                return None
            # Extract clip geometry for picture shape ("crop to shape").
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
        if isinstance(element, Group):
            return None
        return None

    def _render_reversed_paint_order(
        self,
        element,
        shape_id: int,
        metadata: dict[str, object],
        *,
        hyperlink_xml: str,
    ) -> tuple[str, int] | None:
        """Emit stroke-only shape behind fill-only shape for reversed paint order."""
        # Create stroke-only copy (no fill)
        stroke_element = replace(element, fill=None)
        # Create fill-only copy (no stroke)
        fill_element = replace(element, stroke=None)

        # Clear paint_order from metadata to avoid infinite recursion
        clean_meta = dict(metadata)
        clean_meta.pop("paint_order", None)

        # Render stroke-only first (behind)
        stroke_result = self.render(
            stroke_element, shape_id, clean_meta, hyperlink_xml="",
        )
        if stroke_result is None:
            # Stroke-only failed, fall back to normal render
            return self.render(element, shape_id, clean_meta, hyperlink_xml=hyperlink_xml)

        stroke_xml, next_id = stroke_result

        # Render fill-only on top
        fill_result = self.render(
            fill_element, next_id, clean_meta, hyperlink_xml=hyperlink_xml,
        )
        if fill_result is None:
            return stroke_xml, next_id

        fill_xml, final_id = fill_result
        return stroke_xml + fill_xml, final_id

    def _maybe_filter_fallback(
        self,
        element,
        shape_id: int,
        metadata: dict[str, object],
        *,
        hyperlink_xml: str,
    ) -> tuple[str, int] | None:
        if not isinstance(metadata, dict):
            return None
        filters = metadata.get("filters")
        if not isinstance(filters, list) or not filters:
            return None
        policy = metadata.get("policy")
        if not isinstance(policy, dict):
            return None
        media_policy = policy.get("media")
        if not isinstance(media_policy, dict):
            return None
        filter_assets = media_policy.get("filter_assets")
        if not isinstance(filter_assets, dict):
            return None

        filter_meta = metadata.get("filter_metadata")
        if not isinstance(filter_meta, dict):
            filter_meta = {}

        for entry in filters:
            if not isinstance(entry, dict):
                continue
            filter_id = entry.get("id")
            if not isinstance(filter_id, str) or not filter_id:
                continue
            fallback = entry.get("fallback")
            fallback = fallback.lower() if isinstance(fallback, str) else None
            meta = filter_meta.get(filter_id)
            if fallback is None and isinstance(meta, dict):
                filter_type = meta.get("filter_type")
                if isinstance(filter_type, str) and filter_type.lower() in {"composite", "flood"}:
                    fallback = "emf"
            if fallback not in {"emf", "vector", "bitmap", "raster"}:
                continue
            assets = filter_assets.get(filter_id)
            if not isinstance(assets, list):
                continue
            asset_type = "emf" if fallback in {"emf", "vector"} else "raster"
            asset = next(
                (
                    item
                    for item in assets
                    if isinstance(item, dict)
                    and item.get("type") == asset_type
                    and (item.get("data_hex") or item.get("data"))
                ),
                None,
            )
            if asset is None:
                continue
            data_hex = asset.get("data_hex")
            raw_data = asset.get("data")
            if isinstance(data_hex, str) and data_hex:
                image_bytes = bytes.fromhex(data_hex)
            elif isinstance(raw_data, (bytes, bytearray)):
                image_bytes = bytes(raw_data)
            else:
                continue

            bounds = resolve_filter_fallback_bounds(
                getattr(element, "bbox", None),
                meta if isinstance(meta, dict) else None,
            )
            if bounds is None or bounds.width <= 0 or bounds.height <= 0:
                continue

            image_metadata: dict[str, object] = {
                "image_source": "filter_fallback",
                "filter_id": filter_id,
                "fallback": fallback,
            }
            for source in (
                meta if isinstance(meta, dict) else None,
                asset.get("metadata") if isinstance(asset.get("metadata"), dict) else None,
            ):
                if not isinstance(source, dict):
                    continue
                blip_color_transforms = source.get("blip_color_transforms")
                if isinstance(blip_color_transforms, list) and blip_color_transforms:
                    image_metadata["blip_color_transforms"] = list(blip_color_transforms)
                    break
            if asset_type == "emf":
                image_metadata["emf_asset"] = {
                    "relationship_id": asset.get("relationship_id"),
                    "width_emu": asset.get("width_emu"),
                    "height_emu": asset.get("height_emu"),
                }
            origin = Point(bounds.x, bounds.y)
            size_rect = Rect(0.0, 0.0, bounds.width, bounds.height)
            image = Image(
                origin=origin,
                size=size_rect,
                data=image_bytes,
                format="emf" if asset_type == "emf" else "png",
                metadata=image_metadata,
            )
            xml = render_picture(
                image,
                shape_id,
                template=self._picture_template,
                policy_for=self._policy_for,
                register_media=self._register_media,
                hyperlink_xml=hyperlink_xml,
            )
            if xml is None:
                return None
            self._trace_writer(
                "filter_fallback_rendered",
                stage="filter",
                metadata={
                    "shape_id": shape_id,
                    "filter_id": filter_id,
                    "fallback": fallback,
                    "format": image.format,
                },
            )
            return xml, shape_id + 1
        return None

    def _strip_invalid_filter_effects(self, element):
        effects = getattr(element, "effects", None)
        if not effects:
            return element
        cleaned = []
        for effect in effects:
            if isinstance(effect, CustomEffect):
                xml = effect.drawingml or ""
                if _is_invalid_custom_effect_xml(
                    xml,
                    invalid_substrings=self._INVALID_EFFECT_SUBSTRINGS,
                ):
                    continue
            cleaned.append(effect)
        if len(cleaned) == len(effects):
            return element
        try:
            return replace(element, effects=cleaned)
        except TypeError:
            try:
                element.effects = cleaned
            except Exception:  # pragma: no cover - defensive
                return element
            return element
    def _maybe_rasterize(
        self,
        element,
        shape_id: int,
        metadata: dict[str, object],
        *,
        hyperlink_xml: str,
    ) -> tuple[str, int] | None:
        gradient_raster = self._needs_gradient_raster(element)
        if self._rasterizer is None:
            if gradient_raster:
                self._apply_gradient_fallback(element, metadata)
            return None
        policy = metadata.setdefault("policy", {}) if isinstance(metadata, dict) else {}
        geometry_policy = policy.setdefault("geometry", {})
        fallback = geometry_policy.get("suggest_fallback")
        if not gradient_raster and fallback not in {FALLBACK_BITMAP, FALLBACK_RASTERIZE}:
            return None
        if gradient_raster:
            geometry_policy.setdefault("suggest_fallback", FALLBACK_RASTERIZE)
            geometry_policy.setdefault("gradient_rasterize", True)
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

    def _register_pattern_tile(self, element):
        """Register pattern tile images as media and update relationship IDs."""
        fill = getattr(element, "fill", None)
        stroke = getattr(element, "stroke", None)
        updated_fill = None
        updated_stroke = None

        if isinstance(fill, PatternPaint) and fill.tile_image and not fill.tile_relationship_id:
            rid = self._register_tile_image(fill.tile_image)
            if rid:
                updated_fill = replace(fill, tile_relationship_id=rid)

        if stroke is not None:
            paint = getattr(stroke, "paint", None)
            if isinstance(paint, PatternPaint) and paint.tile_image and not paint.tile_relationship_id:
                rid = self._register_tile_image(paint.tile_image)
                if rid:
                    updated_stroke = replace(stroke, paint=replace(paint, tile_relationship_id=rid))

        if updated_fill is None and updated_stroke is None:
            return element

        try:
            kwargs = {}
            if updated_fill is not None:
                kwargs["fill"] = updated_fill
            if updated_stroke is not None:
                kwargs["stroke"] = updated_stroke
            return replace(element, **kwargs)
        except TypeError:
            return element

    def _register_tile_image(self, image_data: bytes) -> str | None:
        """Register tile image bytes as media and return relationship ID."""
        try:
            image = Image(
                origin=Point(0.0, 0.0),
                size=Rect(0.0, 0.0, 1.0, 1.0),
                data=image_data,
                format="png",
                metadata={"image_source": "pattern_tile"},
            )
            return self._register_media(image)
        except Exception:
            self._logger.debug("Failed to register pattern tile image", exc_info=True)
            return None

    def _needs_gradient_raster(self, element) -> bool:
        fill = getattr(element, "fill", None)
        if isinstance(fill, RadialGradientPaint) and fill.policy_decision == "rasterize_nonuniform":
            return True
        stroke = getattr(element, "stroke", None)
        if stroke is not None:
            paint = getattr(stroke, "paint", None)
            if isinstance(paint, RadialGradientPaint) and paint.policy_decision == "rasterize_nonuniform":
                return True
        return False

    def _apply_gradient_fallback(self, element, metadata: dict[str, object]) -> None:
        policy = metadata.setdefault("policy", {}) if isinstance(metadata, dict) else {}
        geometry_policy = policy.setdefault("geometry", {})
        geometry_policy.setdefault("gradient_fallback", "solid")

        fill = getattr(element, "fill", None)
        if isinstance(fill, RadialGradientPaint) and fill.policy_decision == "rasterize_nonuniform":
            element.fill = self._average_gradient_paint(fill)

        stroke = getattr(element, "stroke", None)
        if stroke is not None:
            paint = getattr(stroke, "paint", None)
            if isinstance(paint, RadialGradientPaint) and paint.policy_decision == "rasterize_nonuniform":
                element.stroke = replace(stroke, paint=self._average_gradient_paint(paint))

    def _maybe_clip_overlay(self, element, overlay_shape_id: int) -> str | None:
        """Generate a white EMF overlay with an even-odd cutout for clip paths."""
        clip = getattr(element, "clip", None)
        if clip is None:
            return None
        segments = getattr(clip, "path_segments", None)
        if not segments:
            return None
        bbox = getattr(element, "bbox", None)
        if bbox is None or bbox.width <= 0 or bbox.height <= 0:
            return None

        from .clip_overlay import build_clip_overlay_emf

        emf_bytes = build_clip_overlay_emf(bbox, segments)
        if emf_bytes is None:
            return None

        overlay_image = Image(
            origin=Point(bbox.x, bbox.y),
            size=Rect(0.0, 0.0, bbox.width, bbox.height),
            data=emf_bytes,
            format="emf",
            metadata={"image_source": "clip_overlay"},
        )
        return render_picture(
            overlay_image,
            overlay_shape_id,
            template=self._picture_template,
            policy_for=self._policy_for,
            register_media=self._register_media,
            hyperlink_xml="",
        )

    @staticmethod
    def _average_gradient_paint(paint: RadialGradientPaint) -> SolidPaint:
        if not paint.stops:
            return SolidPaint(rgb="000000", opacity=1.0)
        total_r = total_g = total_b = total_a = 0.0
        for stop in paint.stops:
            token = (stop.rgb or "000000").strip().lstrip("#")
            if len(token) != 6:
                token = "000000"
            try:
                total_r += int(token[0:2], 16)
                total_g += int(token[2:4], 16)
                total_b += int(token[4:6], 16)
            except ValueError:
                total_r += 0.0
                total_g += 0.0
                total_b += 0.0
            total_a += float(stop.opacity)
        count = max(len(paint.stops), 1)
        avg_r = int(round(total_r / count))
        avg_g = int(round(total_g / count))
        avg_b = int(round(total_b / count))
        avg_opacity = total_a / count
        return SolidPaint(rgb=f"{avg_r:02X}{avg_g:02X}{avg_b:02X}", opacity=avg_opacity)


def _intersect_rects(a: Rect, b: Rect) -> Rect | None:
    """Return the intersection of two Rects, or None if they don't overlap."""
    x1 = max(a.x, b.x)
    y1 = max(a.y, b.y)
    x2 = min(a.x + a.width, b.x + b.width)
    y2 = min(a.y + a.height, b.y + b.height)
    if x2 <= x1 or y2 <= y1:
        return None
    return Rect(x1, y1, x2 - x1, y2 - y1)


def _apply_clip_bounds(element, metadata: dict[str, object]):
    """Intersect element bounds with clip bounds for xfrm approximation.

    Consumes ``_clip_bounds`` from *metadata* if present and returns a
    replacement element with tighter bounds when the element type supports it.
    """
    if not isinstance(metadata, dict):
        return element
    clip = metadata.pop("_clip_bounds", None)
    if not isinstance(clip, Rect):
        return element

    bbox = getattr(element, "bbox", None)
    if not isinstance(bbox, Rect):
        return element

    clipped = _intersect_rects(bbox, clip)
    if clipped is None or clipped == bbox:
        return element

    if isinstance(element, Rectangle):
        return replace(element, bounds=clipped)

    if isinstance(element, Image):
        # Compute srcRect crop percentages (thousandths of percent).
        w = max(bbox.width, 1e-9)
        h = max(bbox.height, 1e-9)
        l_pct = int(max(0.0, (clipped.x - bbox.x) / w) * 100_000)
        t_pct = int(max(0.0, (clipped.y - bbox.y) / h) * 100_000)
        r_pct = int(
            max(0.0, ((bbox.x + bbox.width) - (clipped.x + clipped.width)) / w)
            * 100_000
        )
        b_pct = int(
            max(0.0, ((bbox.y + bbox.height) - (clipped.y + clipped.height)) / h)
            * 100_000
        )
        new_elem = replace(
            element,
            origin=Point(clipped.x, clipped.y),
            size=Rect(0.0, 0.0, clipped.width, clipped.height),
        )
        if any((l_pct, t_pct, r_pct, b_pct)):
            new_elem.metadata["_src_rect"] = (l_pct, t_pct, r_pct, b_pct)
        return new_elem

    # Circle, Ellipse, Path — geometry-driven; clip approximation not applied.
    return element


def _is_invalid_custom_effect_xml(
    xml: str,
    *,
    invalid_substrings: tuple[str, ...],
) -> bool:
    lowered = xml.lower()
    stripped = lowered.lstrip()
    if stripped.startswith("<a:solidfill") or stripped.startswith("<solidfill"):
        return True
    return any(marker in lowered for marker in invalid_substrings)


__all__ = ["DrawingMLShapeRenderer"]
