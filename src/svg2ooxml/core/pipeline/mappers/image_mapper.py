"""Mapper converting IR Image nodes into DrawingML picture XML."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from svg2ooxml.drawingml.generator import px_to_emu

# Import centralized XML builders for safe DrawingML generation
from svg2ooxml.drawingml.xml_builder import (
    a_sub,
    graft_xml_fragment,
    p_elem,
    p_sub,
    to_string,
)
from svg2ooxml.ir.scene import Image

from .base import Mapper, MapperResult, OutputFormat
from .clip_render import clip_result_to_xml
from .image_adapter import ImageProcessingAdapter, create_image_adapter


@dataclass
class ImageDecision:
    """Simplified image mapping decision."""

    use_native: bool = True
    format: str = "png"
    confidence: float = 1.0
    estimated_quality: float = 0.98
    estimated_performance: float = 0.9
    has_transparency: bool = False


class ImageMapper(Mapper):
    """Translate ``IR.Image`` nodes into DrawingML picture XML."""

    def __init__(self, policy: Any | None = None, services=None) -> None:
        super().__init__(policy or DefaultImagePolicy())
        self._logger = logging.getLogger(__name__)
        self._services = services
        self._adapter: ImageProcessingAdapter = create_image_adapter(services)
        self._clip_service = None
        if services is not None:
            self._clip_service = getattr(services, "clip_service", None)
            if self._clip_service is None and hasattr(services, "resolve"):
                self._clip_service = services.resolve("clip_service")

    def can_map(self, element: Any) -> bool:
        return isinstance(element, Image)

    def map(self, image: Image) -> MapperResult:
        decision = self._resolve_decision(image)
        processing = self._adapter.process_image(image)

        clip_xml = ""
        clip_metadata = None
        clip_media_files = None
        if getattr(image, "clip", None) is not None and self._clip_service is not None:
            try:
                clip_result = self._clip_service.compute(image.clip)
            except Exception as exc:  # pragma: no cover - defensive
                self._logger.debug("Clip service failed: %s", exc)
                clip_result = None
            if clip_result is not None:
                clip_xml_snippet, clip_metadata, clip_media_files = clip_result_to_xml(clip_result, image.clip)
                clip_xml = clip_xml_snippet or ""

        xml_content = self._build_picture_xml(image, processing.relationship_id, clip_xml)

        media_files = []
        if processing.image_data is not None:
            media_files.append(
                {
                    "relationship_id": processing.relationship_id,
                    "data": processing.image_data,
                    "format": processing.format,
                    "content_type": _content_type(processing.format),
                }
            )
        if clip_media_files:
            media_files.extend(clip_media_files)

        metadata = {
            "relationship_id": processing.relationship_id,
            "format": processing.format,
            "dimensions": (image.size.width, image.size.height),
            "clip": clip_metadata,
            "processing": dict(processing.metadata),
            "opacity": image.opacity,
        }

        return MapperResult(
            element=image,
            output_format=OutputFormat.NATIVE_DML if decision.use_native else OutputFormat.EMF_RASTER,
            xml_content=xml_content,
            policy_decision=decision,
            metadata=metadata,
            media_files=media_files or None,
            estimated_quality=decision.estimated_quality,
            estimated_performance=decision.estimated_performance,
        )

    # ------------------------------------------------------------------ helpers

    def _resolve_decision(self, image: Image) -> ImageDecision:
        policy = getattr(self, "policy", None)
        if policy is not None and hasattr(policy, "decide_image"):
            try:
                decision = policy.decide_image(image)
                if decision is not None:
                    return decision
            except Exception as exc:  # pragma: no cover - defensive
                self._logger.debug("Policy decision failed: %s", exc)
        format_hint = image.format or "png"
        has_transparency = bool(image.opacity < 1.0)
        return ImageDecision(format=format_hint, has_transparency=has_transparency)

    def _build_picture_xml(self, image: Image, rel_id: str, clip_xml: str) -> str:
        origin = image.origin
        bounds = image.size
        x_emu = px_to_emu(origin.x)
        y_emu = px_to_emu(origin.y)
        width_emu = max(1, px_to_emu(bounds.width))
        height_emu = max(1, px_to_emu(bounds.height))

        # Build p:pic with lxml
        pic = p_elem("pic")

        # Build p:nvPicPr
        nvPicPr = p_sub(pic, "nvPicPr")
        p_sub(nvPicPr, "cNvPr", id="1", name="Image")
        cNvPicPr = p_sub(nvPicPr, "cNvPicPr")
        a_sub(cNvPicPr, "picLocks", noChangeAspect="1")
        p_sub(nvPicPr, "nvPr")

        # Build p:blipFill
        blipFill = p_sub(pic, "blipFill")
        blip = a_sub(blipFill, "blip")
        blip.set("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed", rel_id)
        stretch = a_sub(blipFill, "stretch")
        a_sub(stretch, "fillRect")

        # Build p:spPr
        spPr = p_sub(pic, "spPr")
        xfrm = a_sub(spPr, "xfrm")
        a_sub(xfrm, "off", x=x_emu, y=y_emu)
        a_sub(xfrm, "ext", cx=width_emu, cy=height_emu)
        prstGeom = a_sub(spPr, "prstGeom", prst="rect")
        a_sub(prstGeom, "avLst")

        # Add clip_xml if present
        if clip_xml:
            graft_xml_fragment(spPr, clip_xml)

        return to_string(pic)


class DefaultImagePolicy:
    """Fallback policy that always emits native images."""

    def decide_image(self, image: Image) -> ImageDecision:
        format_hint = image.format or "png"
        return ImageDecision(
            use_native=True,
            format=format_hint,
            has_transparency=image.opacity < 1.0,
        )


def _content_type(fmt: str) -> str:
    fmt = (fmt or "").lower()
    if fmt == "png":
        return "image/png"
    if fmt in {"jpg", "jpeg"}:
        return "image/jpeg"
    if fmt == "gif":
        return "image/gif"
    if fmt == "svg":
        return "image/svg+xml"
    return "application/octet-stream"


__all__ = ["ImageMapper", "ImageDecision"]
