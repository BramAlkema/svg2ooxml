"""Structured clip service integration for svg2ooxml."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from svg2ooxml.common.units import UnitConverter
from svg2ooxml.drawingml.bridges.emf_path_adapter import EMFPathAdapter, PathStyle
from svg2ooxml.drawingml.custgeom_generator import segments_from_primitives
from svg2ooxml.drawingml.raster_adapter import RasterAdapter
from svg2ooxml.ir.geometry import Rect, SegmentType
from svg2ooxml.ir.scene import ClipRef
from svg2ooxml.ir.paint import SolidPaint

from svg2ooxml.core.traversal.clip_geometry import (
    ClipComputeResult,
    ClipCustGeom,
    ClipFallback,
    ClipPathSegment,
    ClipMediaMeta,
    compute_clip_geometry,
)

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import a_elem, a_sub, to_string

EMU_PER_PX = 9525


@dataclass
class ClipAnalysis:
    """Lightweight clip analysis placeholder to ease future integration."""

    complexity: str | None = None
    requires_emf: bool = False
    clip_chain: list[Any] | None = None
    fallback_order: tuple[str, ...] | None = None
    policy: dict[str, Any] | None = None


class StructuredClipService:
    """Generate structured clip results for downstream mappers."""

    def __init__(self, services=None, logger: logging.Logger | None = None) -> None:
        self._services = services
        self._logger = logger or logging.getLogger(__name__)
        self._unit_converter = UnitConverter()
        self._emf_adapter = EMFPathAdapter()
        self._raster_adapter = RasterAdapter()

    def compute(
        self,
        clip_ref: ClipRef | None,
        analysis: ClipAnalysis | Any | None = None,
        element_context: dict[str, Any] | None = None,
    ) -> ClipComputeResult | None:
        """Return a structured clip result or ``None`` when unsupported."""

        if clip_ref is None:
            return None

        fallback_order = self._determine_fallback_order(analysis)

        for fallback in fallback_order:
            fallback = fallback.lower()
            if fallback == "native":
                result = self._attempt_native(clip_ref, analysis)
            elif fallback == "mimic":
                result = self._attempt_mimic(clip_ref, analysis, element_context)
            elif fallback in {"emf", "policy_emf"}:
                result = self._attempt_emf(clip_ref, analysis, forced=fallback == "policy_emf")
            elif fallback in {"raster", "policy_raster"}:
                result = self._attempt_raster(clip_ref, analysis, element_context, forced=fallback == "policy_raster")
            else:
                continue

            if result is not None:
                return result

        self._logger.debug("Clip %s could not be resolved using fallback order %s", getattr(clip_ref, "clip_id", None), fallback_order)
        return None

    def _extract_bounds(
        self,
        clip_ref: ClipRef,
        element_context: Optional[dict[str, Any]],
    ) -> Optional[Rect]:
        bbox = getattr(clip_ref, "bounding_box", None)
        if bbox is None and element_context:
            ctx_bbox = element_context.get("bounding_box")
            if isinstance(ctx_bbox, Rect):
                bbox = ctx_bbox
        return bbox

    def _rect_to_custgeom(self, bbox: Rect, *, even_odd: bool) -> ClipCustGeom:
        x = bbox.x
        y = bbox.y
        w = max(bbox.width, 0.0)
        h = max(bbox.height, 0.0)

        points = [
            ClipPathSegment("moveTo", [x, y]),
            ClipPathSegment("lnTo", [x + w, y]),
            ClipPathSegment("lnTo", [x + w, y + h]),
            ClipPathSegment("lnTo", [x, y + h]),
            ClipPathSegment("close", []),
        ]

        # Build a:custGeom with lxml
        custGeom = a_elem("custGeom")
        pathLst = a_sub(custGeom, "pathLst")
        path = a_sub(pathLst, "path", w=_to_emu(w), h=_to_emu(h), fill="none")

        # moveTo
        moveTo = a_sub(path, "moveTo")
        a_sub(moveTo, "pt", x=_to_emu(0), y=_to_emu(0))

        # lnTo corners
        lnTo1 = a_sub(path, "lnTo")
        a_sub(lnTo1, "pt", x=_to_emu(w), y=_to_emu(0))

        lnTo2 = a_sub(path, "lnTo")
        a_sub(lnTo2, "pt", x=_to_emu(w), y=_to_emu(h))

        lnTo3 = a_sub(path, "lnTo")
        a_sub(lnTo3, "pt", x=_to_emu(0), y=_to_emu(h))

        # close
        a_sub(path, "close")

        xml = to_string(custGeom)

        return ClipCustGeom(
            path=points,
            path_xml=xml,
            fill_rule_even_odd=even_odd,
            bbox_emu=_rect_to_emu_tuple(bbox),
        )

    def _is_even_odd(self, clip_ref: ClipRef, analysis: Any | None) -> bool:
        rule = getattr(clip_ref, "clip_rule", None)
        if rule:
            return str(rule).lower() == "evenodd"

        clip_chain = getattr(analysis, "clip_chain", []) if analysis is not None else []
        for clip_def in clip_chain or []:
            clip_rule = getattr(clip_def, "clip_rule", None)
            if clip_rule:
                return str(clip_rule).lower() == "evenodd"
        return False

    def _determine_fallback_order(self, analysis: ClipAnalysis | Any | None) -> tuple[str, ...]:
        if analysis is not None:
            if getattr(analysis, "requires_emf", False):
                return ("emf", "raster")
            order = getattr(analysis, "fallback_order", None)
            if order:
                return tuple(str(item).lower() for item in order if item)
            policy = getattr(analysis, "policy", None)
            if isinstance(policy, dict) and "fallback_order" in policy:
                return tuple(str(item).lower() for item in policy["fallback_order"] if item)
        return ("native", "mimic", "emf", "raster")

    def _attempt_native(self, clip_ref: ClipRef, analysis: ClipAnalysis | Any | None) -> ClipComputeResult | None:
        result = compute_clip_geometry(clip_ref)
        if result is None or result.custgeom is None:
            return None
        fill_rule = self._is_even_odd(clip_ref, analysis)
        result.custgeom.fill_rule_even_odd = fill_rule
        if result.custgeom.bbox_emu is None:
            bbox = getattr(clip_ref, "bounding_box", None)
            if bbox is not None:
                result.custgeom.bbox_emu = _rect_to_emu_tuple(bbox)
        return result

    def _attempt_mimic(
        self,
        clip_ref: ClipRef,
        analysis: ClipAnalysis | Any | None,
        element_context: dict[str, Any] | None,
    ) -> ClipComputeResult | None:
        bbox = self._extract_bounds(clip_ref, element_context)
        if bbox is None:
            segments = self._collect_segments(clip_ref)
            bbox = self._segment_bounds(segments)
        if bbox is None:
            return None

        custgeom = self._rect_to_custgeom(bbox, even_odd=self._is_even_odd(clip_ref, analysis))
        metadata = {"source": "bounding_box"}
        return ClipComputeResult(
            strategy=ClipFallback.MIMIC,
            custgeom=custgeom,
            used_bbox_rect=True,
            metadata=metadata,
        )

    def _attempt_emf(
        self,
        clip_ref: ClipRef,
        analysis: ClipAnalysis | Any | None,
        *,
        forced: bool = False,
    ) -> ClipComputeResult | None:
        segments = self._collect_segments(clip_ref)
        if not segments:
            return None
        bounds = self._segment_bounds(segments)
        if bounds is None or bounds.width <= 0 or bounds.height <= 0:
            return None

        context = self._unit_converter.create_context(width=bounds.width, height=bounds.height)
        style = PathStyle(
            fill=SolidPaint("FFFFFF"),
            fill_rule="evenodd" if self._is_even_odd(clip_ref, analysis) else "nonzero",
            stroke=None,
        )
        emf_result = self._emf_adapter.render(
            segments=segments,
            style=style,
            unit_converter=self._unit_converter,
            conversion_context=context,
            dpi=int(round(context.dpi)),
        )
        if emf_result is None or not emf_result.emf_bytes:
            return None

        metadata = {
            "source": "emf_fallback",
            "forced": forced,
            "width_emu": emf_result.width_emu,
            "height_emu": emf_result.height_emu,
        }
        media = ClipMediaMeta(
            content_type="image/x-emf",
            rel_id=None,
            part_name=None,
            bbox_emu=(0, 0, emf_result.width_emu, emf_result.height_emu),
            data=emf_result.emf_bytes,
            description="clip-emf-fallback",
        )
        return ClipComputeResult(
            strategy=ClipFallback.EMF_SHAPE,
            metadata=metadata,
            used_bbox_rect=False,
            media=media,
            xml_placeholder="<!-- svg2ooxml:clip-fallback emf -->",
        )

    def _attempt_raster(
        self,
        clip_ref: ClipRef,
        analysis: ClipAnalysis | Any | None,
        element_context: dict[str, Any] | None,
        *,
        forced: bool = False,
    ) -> ClipComputeResult | None:
        bbox = self._extract_bounds(clip_ref, element_context)
        if bbox is None:
            segments = self._collect_segments(clip_ref)
            bbox = self._segment_bounds(segments)
        if bbox is None:
            return None

        width_px = max(1, int(round(bbox.width or 1.0)))
        height_px = max(1, int(round(bbox.height or 1.0)))
        placeholder = self._raster_adapter.generate_placeholder(
            width_px=width_px,
            height_px=height_px,
            metadata={
                "source": "clip_fallback",
                "clip_id": getattr(clip_ref, "clip_id", None),
                "forced": forced,
            },
        )
        media = ClipMediaMeta(
            content_type="image/png",
            rel_id=placeholder.relationship_id,
            part_name=None,
            bbox_emu=(_to_emu(0), _to_emu(0), _to_emu(width_px), _to_emu(height_px)),
            data=placeholder.image_bytes,
            description="clip-raster-fallback",
        )
        metadata = dict(placeholder.metadata or {})
        metadata["source"] = "raster_fallback"
        metadata["forced"] = forced
        return ClipComputeResult(
            strategy=ClipFallback.BITMAP,
            metadata=metadata,
            used_bbox_rect=True,
            media=media,
            xml_placeholder="<!-- svg2ooxml:clip-fallback raster -->",
        )

    def _collect_segments(self, clip_ref: ClipRef) -> list[SegmentType]:
        segments: list[SegmentType] = []
        if clip_ref.path_segments:
            segments.extend(clip_ref.path_segments)
        if clip_ref.primitives:
            segments.extend(segments_from_primitives(clip_ref.primitives))
        return segments

    def _segment_bounds(self, segments: Sequence[SegmentType] | None) -> Rect | None:
        if not segments:
            return None
        xs: list[float] = []
        ys: list[float] = []
        for segment in segments:
            for attr in ("start", "end", "control1", "control2"):
                point = getattr(segment, attr, None)
                if point is not None:
                    xs.append(point.x)
                    ys.append(point.y)
        if not xs or not ys:
            return None
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return Rect(min_x, min_y, max_x - min_x, max_y - min_y)


def _rect_to_emu_tuple(rect: Rect) -> tuple[int, int, int, int]:
    return (
        _to_emu(rect.x),
        _to_emu(rect.y),
        _to_emu(rect.width),
        _to_emu(rect.height),
    )


def _to_emu(value: float) -> int:
    return int(round(value * EMU_PER_PX))


__all__ = ["StructuredClipService", "ClipAnalysis"]
