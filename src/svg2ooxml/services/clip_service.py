"""Structured clip service integration for svg2ooxml."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.scene import ClipRef

from svg2ooxml.map.mapper.clip_geometry import (
    ClipComputeResult,
    ClipCustGeom,
    ClipFallback,
    ClipPathSegment,
    compute_clip_geometry,
)

EMU_PER_PX = 9525


@dataclass
class ClipAnalysis:
    """Lightweight clip analysis placeholder to ease future integration."""

    complexity: str | None = None
    requires_emf: bool = False
    clip_chain: list[Any] | None = None


class StructuredClipService:
    """Generate structured clip results for downstream mappers."""

    def __init__(self, services=None, logger: logging.Logger | None = None) -> None:
        self._services = services
        self._logger = logger or logging.getLogger(__name__)

    def compute(
        self,
        clip_ref: ClipRef | None,
        analysis: ClipAnalysis | Any | None = None,
        element_context: dict[str, Any] | None = None,
    ) -> ClipComputeResult | None:
        """Return a structured clip result or ``None`` when unsupported."""

        if clip_ref is None:
            return None

        if analysis is not None and getattr(analysis, "requires_emf", False):
            return ClipComputeResult(strategy=ClipFallback.EMF_SHAPE, used_bbox_rect=False)

        result = compute_clip_geometry(clip_ref)
        if result is not None and result.custgeom is not None:
            fill_rule = self._is_even_odd(clip_ref, analysis)
            result.custgeom.fill_rule_even_odd = fill_rule
            if result.custgeom.bbox_emu is None:
                bbox = getattr(clip_ref, "bounding_box", None)
                if bbox is not None:
                    result.custgeom.bbox_emu = _rect_to_emu_tuple(bbox)
            return result

        bbox = self._extract_bounds(clip_ref, element_context)
        if bbox is None:
            return None

        custgeom = self._rect_to_custgeom(bbox, even_odd=self._is_even_odd(clip_ref, analysis))
        return ClipComputeResult(
            strategy=ClipFallback.NONE,
            custgeom=custgeom,
            used_bbox_rect=True,
            metadata={"source": "bounding_box"},
        )

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

        xml = (
            "<a:custGeom>"
            "<a:pathLst>"
            f"<a:path w=\"{_to_emu(w)}\" h=\"{_to_emu(h)}\" fill=\"none\">"
            f"<a:moveTo><a:pt x=\"{_to_emu(0)}\" y=\"{_to_emu(0)}\"/></a:moveTo>"
            f"<a:lnTo><a:pt x=\"{_to_emu(w)}\" y=\"{_to_emu(0)}\"/></a:lnTo>"
            f"<a:lnTo><a:pt x=\"{_to_emu(w)}\" y=\"{_to_emu(h)}\"/></a:lnTo>"
            f"<a:lnTo><a:pt x=\"{_to_emu(0)}\" y=\"{_to_emu(h)}\"/></a:lnTo>"
            "<a:close/>"
            "</a:path>"
            "</a:pathLst>"
            "</a:custGeom>"
        )

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
