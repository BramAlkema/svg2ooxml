"""Mapper for IR Path elements to DrawingML."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from svg2ooxml.drawingml.generator import DrawingMLPathGenerator
from svg2ooxml.common.units import px_to_emu
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
        geometry_xml = geometry.xml
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
        fill_xml = _fill_xml(path)
        stroke_xml = _stroke_xml(path)
        xml = (
            f"<p:sp>"
            f"<p:nvSpPr><p:cNvPr id=\"1\" name=\"Path\"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
            f"<p:spPr>"
            f"<a:xfrm>"
            f"<a:off x=\"{px_to_emu(bounds.x)}\" y=\"{px_to_emu(bounds.y)}\"/>"
            f"<a:ext cx=\"{px_to_emu(bounds.width or 1.0)}\" cy=\"{px_to_emu(bounds.height or 1.0)}\"/>"
            f"</a:xfrm>"
            f"{clip_xml}"
            f"{geometry_xml}"
            f"{fill_xml}"
            f"{stroke_xml}"
            f"</p:spPr>"
            f"</p:sp>"
        )

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


def _fill_xml(path: Path) -> str:
    fill = getattr(path, "fill", None)
    if fill is None:
        return "<a:noFill/>"
    rgb = getattr(fill, "rgb", "000000")
    opacity = getattr(fill, "opacity", 1.0)
    alpha = int(max(0.0, min(1.0, opacity)) * 100000)
    return (
        "<a:solidFill>"
        f"<a:srgbClr val=\"{rgb}\">"
        f"<a:alpha val=\"{alpha}\"/>"
        "</a:srgbClr>"
        "</a:solidFill>"
    )


def _stroke_xml(path: Path) -> str:
    stroke = getattr(path, "stroke", None)
    if stroke is None:
        return "<a:ln><a:noFill/></a:ln>"
    paint = getattr(stroke, "paint", None)
    rgb = getattr(paint, "rgb", "000000") if paint else "000000"
    opacity = getattr(paint, "opacity", getattr(stroke, "opacity", 1.0))
    alpha = int(max(0.0, min(1.0, opacity)) * 100000)
    width = getattr(stroke, "width", 1.0) or 1.0
    return (
        f"<a:ln w=\"{px_to_emu(width)}\">"
        f"<a:solidFill><a:srgbClr val=\"{rgb}\"><a:alpha val=\"{alpha}\"/></a:srgbClr></a:solidFill>"
        "</a:ln>"
    )


__all__ = ["PathMapper", "PathDecision"]
