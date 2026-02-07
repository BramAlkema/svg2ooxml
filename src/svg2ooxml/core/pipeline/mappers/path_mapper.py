"""Mapper for IR Path elements to DrawingML."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

# Import centralized XML builders for safe DrawingML generation
from lxml import etree

from svg2ooxml.common.conversions.opacity import opacity_to_ppt
from svg2ooxml.common.units import px_to_emu
from svg2ooxml.drawingml.generator import DrawingMLPathGenerator
from svg2ooxml.drawingml.xml_builder import (
    a_elem,
    a_sub,
    graft_xml_fragment,
    ln,
    no_fill,
    p_elem,
    p_sub,
    solid_fill,
    to_string,
)
from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.scene import Path

from .base import Mapper, MapperResult, OutputFormat
from .clip_render import clip_result_to_xml


@dataclass
class PathDecision:
    use_native: bool = True
    confidence: float = 1.0
    estimated_quality: float = 0.98
    estimated_performance: float = 0.9


class PathMapper(Mapper):
    """Translate ``IR.Path`` nodes into DrawingML or EMF fallbacks."""

    def __init__(self, policy: Any | None = None, services=None) -> None:
        super().__init__(policy or DefaultPathPolicy())
        self._logger = logging.getLogger(__name__)
        self._services = services
        self._path_generator = DrawingMLPathGenerator()
        self._clip_service = None
        if services is not None:
            self._clip_service = getattr(services, "clip_service", None)
            if self._clip_service is None and hasattr(services, "resolve"):
                self._clip_service = services.resolve("clip_service")

    def can_map(self, element: Any) -> bool:
        return isinstance(element, Path)

    def map(self, path: Path) -> MapperResult:
        decision = self._resolve_decision(path)
        if decision.use_native:
            return self._map_to_drawingml(path, decision)
        return self._map_to_emf(path, decision)

    def _resolve_decision(self, path: Path) -> PathDecision:
        policy = getattr(self, "policy", None)
        if policy is not None and hasattr(policy, "decide_path"):
            try:
                decision = policy.decide_path(path)
                if decision is not None:
                    return decision
            except Exception as exc:  # pragma: no cover - defensive
                self._logger.debug("Path policy failed: %s", exc)
        return PathDecision()

    def _map_to_drawingml(self, path: Path, decision: PathDecision) -> MapperResult:
        geometry = self._path_generator.generate_custom_geometry(
            path.segments,
            closed=path.is_closed,
            fill_mode="solid" if path.fill else "none",
            stroke_mode="solid" if path.stroke else "none",
        )
        geometry_elem = geometry.element
        clip_xml = ""
        metadata = {}
        media_files = None
        if path.clip and self._clip_service is not None:
            try:
                clip_result = self._clip_service.compute(path.clip)
                clip_xml, clip_meta, clip_media = clip_result_to_xml(clip_result, path.clip)
                if clip_meta:
                    metadata["clip"] = clip_meta
                media_files = clip_media
            except Exception as exc:  # pragma: no cover - defensive
                self._logger.debug("Clip processing failed: %s", exc)

        bounds = _path_bounds(path)

        # Build p:sp with lxml
        sp = p_elem("sp")

        # Build p:nvSpPr
        nvSpPr = p_sub(sp, "nvSpPr")
        p_sub(nvSpPr, "cNvPr", id="1", name="Path")
        p_sub(nvSpPr, "cNvSpPr")
        p_sub(nvSpPr, "nvPr")

        # Build p:spPr
        spPr = p_sub(sp, "spPr")

        # Build a:xfrm
        xfrm = a_sub(spPr, "xfrm")
        a_sub(xfrm, "off", x=px_to_emu(bounds.x), y=px_to_emu(bounds.y))
        a_sub(xfrm, "ext", cx=px_to_emu(bounds.width or 1.0), cy=px_to_emu(bounds.height or 1.0))

        # Add clip_xml if present
        if clip_xml:
            graft_xml_fragment(spPr, clip_xml)

        # Add geometry element
        if geometry_elem is not None:
            spPr.append(geometry_elem)

        # Add fill and stroke
        spPr.append(_fill_elem(path))
        spPr.append(_stroke_elem(path))

        xml = to_string(sp)

        metadata.update(
            {
                "segment_count": len(path.segments),
                "closed": path.is_closed,
            }
        )

        return MapperResult(
            element=path,
            output_format=OutputFormat.NATIVE_DML,
            xml_content=xml,
            policy_decision=decision,
            metadata=metadata,
            media_files=media_files,
        )

    def _map_to_emf(self, path: Path, decision: PathDecision) -> MapperResult:
        # Basic EMF fallback placeholder; real implementation would call EMF adapter
        xml = """<p:sp><p:nvSpPr><p:cNvPr id=\"1\" name=\"PathEMF\"/></p:nvSpPr><p:spPr/></p:sp>"""
        metadata = {"fallback": "emf"}
        return MapperResult(
            element=path,
            output_format=OutputFormat.EMF_VECTOR,
            xml_content=xml,
            policy_decision=decision,
            metadata=metadata,
        )


class DefaultPathPolicy:
    def decide_path(self, path: Path) -> PathDecision:
        return PathDecision(use_native=True)


def _path_bounds(path: Path) -> Rect:
    bbox = getattr(path, "bbox", None)
    if bbox is None:
        return Rect(0.0, 0.0, 1.0, 1.0)
    return bbox


def _fill_elem(path: Path) -> etree._Element:
    fill = getattr(path, "fill", None)
    if fill is None:
        return no_fill()
    rgb = getattr(fill, "rgb", "000000")
    opacity = getattr(fill, "opacity", 1.0)
    alpha = opacity_to_ppt(opacity)
    return solid_fill(rgb, alpha=alpha)


def _stroke_elem(path: Path) -> etree._Element:
    stroke = getattr(path, "stroke", None)
    if stroke is None:
        line = a_elem("ln")
        a_sub(line, "noFill")
        return line
    paint = getattr(stroke, "paint", None)
    rgb = getattr(paint, "rgb", "000000") if paint else "000000"
    opacity = getattr(paint, "opacity", getattr(stroke, "opacity", 1.0))
    alpha = opacity_to_ppt(opacity)
    width = getattr(stroke, "width", 1.0) or 1.0
    return ln(px_to_emu(width), solid_fill(rgb, alpha=alpha))


__all__ = ["PathMapper", "PathDecision"]
