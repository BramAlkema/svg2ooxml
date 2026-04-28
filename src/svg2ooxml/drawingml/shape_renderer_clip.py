"""Clip overlay helpers for DrawingML shape rendering."""

from __future__ import annotations

from svg2ooxml.ir.geometry import Point, Rect
from svg2ooxml.ir.scene import Image

from .image import render_picture


class ShapeRendererClipMixin:
    """Render EMF clip overlays for path elements with even-odd cutouts."""

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


__all__ = ["ShapeRendererClipMixin"]
