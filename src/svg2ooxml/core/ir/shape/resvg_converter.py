"""Resvg path generation methods for shape conversion."""

from __future__ import annotations

from typing import Any

from lxml import etree

from svg2ooxml.core.styling.style_extractor import StyleResult
from svg2ooxml.ir.geometry import SegmentType
from svg2ooxml.ir.scene import ClipRef, MaskInstance, MaskRef, Path
from svg2ooxml.policy.constants import FALLBACK_BITMAP, FALLBACK_EMF
from svg2ooxml.policy.geometry import apply_geometry_policy


class ShapeResvgPathMixin:
    """Mixin housing resvg-specific path assembly logic."""

    def _resvg_segments_to_path(
        self,
        *,
        element: etree._Element,
        segments: list[SegmentType],
        coord_space,
        style: StyleResult,
        metadata: dict[str, Any],
        clip_ref: ClipRef | None,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
    ):
        policy = self._policy_options("geometry")
        if metadata.get("wordart") or metadata.get("resvg_text"):
            policy = (
                {**policy, "simplify_paths": False}
                if policy
                else {"simplify_paths": False}
            )
        allow_emf_fallback, allow_bitmap_fallback = self._geometry_fallback_flags(
            policy
        )
        segments, geom_meta, render_mode = apply_geometry_policy(list(segments), policy)
        bitmap_limits = self._bitmap_fallback_limits(policy)
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
                    (
                        emf_image.metadata
                        if isinstance(emf_image.metadata, dict)
                        else metadata
                    ),
                )
                return emf_image
            if allow_bitmap_fallback:
                self._logger.warning(
                    "Failed to build EMF fallback; attempting bitmap fallback."
                )
                fallback_to_bitmap = True
            else:
                self._logger.warning(
                    "Failed to build EMF fallback; bitmap fallback disabled."
                )

        if (
            render_mode == FALLBACK_BITMAP or fallback_to_bitmap
        ) and allow_bitmap_fallback:
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
                    geometry_policy = metadata.setdefault("policy", {}).setdefault(
                        "geometry", {}
                    )
                    geometry_policy["render_mode"] = FALLBACK_BITMAP
                self._process_mask_metadata(bitmap_image)
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
        elif render_mode == FALLBACK_BITMAP and not allow_bitmap_fallback:
            self._logger.warning(
                "Bitmap fallback disabled; falling back to native rendering."
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
        self._process_mask_metadata(path_object)
        self._apply_marker_metadata(element, path_object.metadata)
        self._trace_geometry_decision(element, "resvg", path_object.metadata)
        marker_shapes = self._build_marker_shapes(element, path_object)
        if marker_shapes:
            return [path_object, *marker_shapes]
        return path_object
