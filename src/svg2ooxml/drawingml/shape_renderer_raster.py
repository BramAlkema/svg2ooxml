"""Raster and gradient fallback helpers for DrawingML shape rendering."""

from __future__ import annotations

from dataclasses import replace

from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.paint import RadialGradientPaint
from svg2ooxml.ir.scene import Image
from svg2ooxml.policy.constants import FALLBACK_BITMAP, FALLBACK_RASTERIZE

from .image import render_picture
from .shape_renderer_utils import average_gradient_paint


class ShapeRendererRasterMixin:
    """Rasterize shapes when policy or gradient limits require bitmap output."""

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
            return None
        geometry_policy = self._geometry_policy(metadata)
        fallback = geometry_policy.get("suggest_fallback")
        if (
            not gradient_raster
            and fallback not in {FALLBACK_BITMAP, FALLBACK_RASTERIZE}
        ):
            return None
        if gradient_raster:
            geometry_policy.setdefault("suggest_fallback", FALLBACK_RASTERIZE)
            geometry_policy.setdefault("gradient_rasterize", True)
        try:
            result = self._rasterizer.rasterize(element)
        except Exception:  # pragma: no cover - defensive
            self._logger.debug(
                "Rasterization failed for %s",
                type(element).__name__,
                exc_info=True,
            )
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
        geometry_policy.setdefault("rasterized_media", []).append(
            {"shape_id": shape_id, "format": "png"}
        )
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

    def _needs_gradient_raster(self, element) -> bool:
        fill = getattr(element, "fill", None)
        if (
            isinstance(fill, RadialGradientPaint)
            and fill.policy_decision == "rasterize_nonuniform"
        ):
            return True
        stroke = getattr(element, "stroke", None)
        if stroke is not None:
            paint = getattr(stroke, "paint", None)
            if (
                isinstance(paint, RadialGradientPaint)
                and paint.policy_decision == "rasterize_nonuniform"
            ):
                return True
        return False

    def _apply_gradient_fallback(self, element, metadata: dict[str, object]):
        geometry_policy = self._geometry_policy(metadata)
        geometry_policy.setdefault("gradient_fallback", "solid")

        updates = {}
        fill = getattr(element, "fill", None)
        if (
            isinstance(fill, RadialGradientPaint)
            and fill.policy_decision == "rasterize_nonuniform"
        ):
            updates["fill"] = average_gradient_paint(fill)

        stroke = getattr(element, "stroke", None)
        if stroke is not None:
            paint = getattr(stroke, "paint", None)
            if (
                isinstance(paint, RadialGradientPaint)
                and paint.policy_decision == "rasterize_nonuniform"
            ):
                updates["stroke"] = replace(stroke, paint=average_gradient_paint(paint))

        if not updates:
            return element
        try:
            return replace(element, **updates)
        except TypeError:
            for key, value in updates.items():
                try:
                    setattr(element, key, value)
                except Exception:  # pragma: no cover - defensive
                    return element
            return element

    def _geometry_policy(self, metadata: dict[str, object]) -> dict[str, object]:
        if not isinstance(metadata, dict):
            return {}
        policy = metadata.get("policy")
        if not isinstance(policy, dict):
            policy = {}
            metadata["policy"] = policy
        geometry_policy = policy.get("geometry")
        if not isinstance(geometry_policy, dict):
            geometry_policy = {}
            policy["geometry"] = geometry_policy
        return geometry_policy


__all__ = ["ShapeRendererRasterMixin"]
