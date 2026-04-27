"""Fallback and mask processing mixin for shape conversion."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from lxml import etree

from svg2ooxml.color.adapters import hex_to_rgb_tuple
from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.common.units import UnitConverter
from svg2ooxml.core.ir import fallbacks
from svg2ooxml.core.ir.shape_converters_utils import _bezier_point, _resolve_svg_length
from svg2ooxml.core.masks.baker import try_bake_mask
from svg2ooxml.core.styling.style_extractor import StyleResult
from svg2ooxml.core.traversal import marker_runtime
from svg2ooxml.core.traversal.constants import DEFAULT_TOLERANCE
from svg2ooxml.core.traversal.coordinate_space import CoordinateSpace
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, Point, SegmentType
from svg2ooxml.ir.paint import SolidPaint
from svg2ooxml.ir.scene import ClipRef, Image, MaskInstance, MaskRef, Path


class ShapeFallbackMixin:
    def _process_mask_metadata(self, ir_object: Any) -> None:
        if ir_object is None or not hasattr(ir_object, "mask"):
            return
        mask_ref = getattr(ir_object, "mask", None)
        if mask_ref is None:
            return
            
        # Attempt to bake the mask into the fill (Wild Idea!)
        if hasattr(ir_object, "fill") and isinstance(ir_object.fill, SolidPaint):
            new_fill, new_mask_ref = try_bake_mask(
                ir_object.fill, 
                mask_ref, 
                services=getattr(self, "_services", None),
                doc_root=getattr(self, "_svg_root", None)
            )
            if new_fill is not ir_object.fill:
                # We baked it! Update the object (bypassing frozen state)
                object.__setattr__(ir_object, "fill", new_fill)
                object.__setattr__(ir_object, "mask", new_mask_ref)
                
                # If we successfully updated and mask is now None, we are done!
                if ir_object.mask is None:
                    return

        processor = getattr(self, "_mask_processor", None)
        if processor is None:
            return
        policy_options = self._policy_options("mask")
        result = processor.process(ir_object, policy_options=policy_options)
        metadata = getattr(ir_object, "metadata", None)
        if isinstance(metadata, dict) and result.metadata:
            mask_meta = metadata.setdefault("mask", {})
            mask_meta.update(result.metadata)
            if result.xml_fragment:
                mask_meta.setdefault("geometry_xml", result.xml_fragment)
        if isinstance(metadata, dict) and result.requires_emf:
            policy_meta = metadata.setdefault("policy", {}).setdefault("geometry", {})
            policy_meta.setdefault("suggest_fallback", "emf")
        if isinstance(metadata, dict):
            self._attach_policy_metadata(metadata, "mask")

    def _convert_path_to_emf(
        self,
        *,
        element: etree._Element,
        style: StyleResult,
        segments: list[SegmentType],
        coord_space: CoordinateSpace,
        clip_ref: ClipRef | None,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
        metadata: dict[str, Any],
    ) -> Image | None:
        adapter = self._get_emf_adapter()
        return fallbacks.render_emf_fallback(
            element=element,
            style=style,
            segments=segments,
            coord_space=coord_space,
            clip_ref=clip_ref,
            mask_ref=mask_ref,
            mask_instance=mask_instance,
            metadata=metadata,
            unit_converter=self._unit_converter,
            conversion_context=self._conversion_context,
            adapter=adapter,
        )

    def _convert_path_to_bitmap(
        self,
        *,
        element: etree._Element,
        style: StyleResult,
        segments: list[SegmentType],
        coord_space: CoordinateSpace,
        clip_ref: ClipRef | None,
        mask_ref: MaskRef | None,
        mask_instance: MaskInstance | None,
        metadata: dict[str, Any],
        bitmap_limits: tuple[int | None, int | None] | None,
    ) -> Image | None:
        max_area_px, max_side_px = bitmap_limits if bitmap_limits is not None else (None, None)
        return fallbacks.render_bitmap_fallback(
            element=element,
            style=style,
            segments=segments,
            coord_space=coord_space,
            clip_ref=clip_ref,
            mask_ref=mask_ref,
            mask_instance=mask_instance,
            metadata=metadata,
            flatten_segments=self._flatten_segments,
            hex_to_rgba=self._hex_to_rgba,
            max_area_px=max_area_px,
            max_side_px=max_side_px,
            logger=self._logger,
        )

    def _flatten_segments(self, segments: Iterable[SegmentType], samples: int = 12) -> list[Point]:
        points: list[Point] = []
        for segment in segments:
            if isinstance(segment, LineSegment):
                if not points:
                    points.append((segment.start.x, segment.start.y))
                points.append((segment.end.x, segment.end.y))
            elif isinstance(segment, BezierSegment):
                if not points:
                    points.append((segment.start.x, segment.start.y))
                for i in range(1, samples + 1):
                    t = i / samples
                    x, y = _bezier_point(segment, t)
                    points.append((x, y))
            else:
                start = getattr(segment, "start", None)
                if start is not None:
                    points.append((start.x, start.y))
        return points

    @staticmethod
    def _hex_to_rgba(rgb: str, opacity: float) -> tuple[int, int, int, int]:
        r, g, b = hex_to_rgb_tuple(rgb)
        a = max(0, min(255, int(round(opacity * 255))))
        return (r, g, b, a)

    def _apply_marker_metadata(
        self,
        element: etree._Element,
        metadata: dict[str, Any],
    ) -> None:
        marker_runtime.apply_marker_metadata(self, element, metadata)

    def _build_marker_shapes(
        self,
        element: etree._Element,
        path: Path,
    ) -> list[Path]:
        return marker_runtime.build_marker_shapes(
            self,
            element,
            path,
            tolerance=DEFAULT_TOLERANCE,
        )

    def _transform_segments(
        self,
        segments: list[SegmentType],
        matrix: Matrix2D,
    ) -> list[SegmentType]:
        transformed: list[SegmentType] = []
        for segment in segments:
            if isinstance(segment, LineSegment):
                start = matrix.transform_point(segment.start)
                end = matrix.transform_point(segment.end)
                transformed.append(LineSegment(start=start, end=end))
            elif isinstance(segment, BezierSegment):
                transformed.append(
                    BezierSegment(
                        start=matrix.transform_point(segment.start),
                        control1=matrix.transform_point(segment.control1),
                        control2=matrix.transform_point(segment.control2),
                        end=matrix.transform_point(segment.end),
                    )
                )
            else:
                transformed.append(segment)
        return transformed

    def _get_emf_adapter(self):
        adapter = getattr(self, "_emf_adapter", None)
        if adapter is not None:
            return adapter
        services = getattr(self, "_services", None)
        if services is None:
            return None
        adapter = getattr(services, "emf_path_adapter", None)
        if adapter is None and hasattr(services, "resolve"):
            adapter = services.resolve("emf_path_adapter")
        if adapter is not None:
            self._emf_adapter = adapter
        return adapter

    def _resolve_dimension_preference(
        self,
        primary: str | None,
        fallback: str | None,
        context,
        *,
        axis: str,
    ) -> float | None:
        value = self._resolve_length(primary, context, axis=axis)
        if value not in (None, 0.0):
            return value
        value = self._resolve_length(fallback, context, axis=axis)
        if value in (None, 0.0):
            return None
        return value

    def _resolve_length(
        self,
        value: str | None,
        context,
        *,
        axis: str,
    ) -> float:
        if value in (None, "", "0"):
            return 0.0
        unit_converter = getattr(self, "_unit_converter", None) or UnitConverter()
        resolved = _resolve_svg_length(
            unit_converter,
            value,
            context,
            axis=axis,
            default=0.0,
        )
        return 0.0 if resolved is None else resolved
