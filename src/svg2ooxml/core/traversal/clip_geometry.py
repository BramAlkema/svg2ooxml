"""Clip geometry computation utilities shared across converters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from svg2ooxml.common.geometry.clip import (
    ClipPathSegment,
    rect_to_emu,
    tessellate_segments,
)
from svg2ooxml.drawingml.custgeom_generator import (
    CustGeomGenerator,
    segments_from_primitives,
)
from svg2ooxml.ir.geometry import SegmentType
from svg2ooxml.ir.scene import ClipRef, MaskDefinition, MaskRef

_CUST_GEOM_GENERATOR = CustGeomGenerator()


class ClipFallback(Enum):
    """Fallback modes for clip emission."""

    NONE = "native"
    MIMIC = "mimic"
    EMF_SHAPE = "emf_shape"
    EMF_GROUP = "emf_group"
    BITMAP = "bitmap"


@dataclass
class ClipCustGeom:
    """Custom geometry payload for clips."""

    path: list[ClipPathSegment] = field(default_factory=list)
    path_xml: str | None = None
    fill_rule_even_odd: bool = False
    bbox_emu: tuple[int, int, int, int] | None = None


@dataclass
class ClipMediaMeta:
    """Metadata describing generated media assets."""

    content_type: str
    rel_id: str | None
    part_name: str | None
    bbox_emu: tuple[int, int, int, int]
    data: bytes | None = None
    description: str | None = None


@dataclass
class ClipComputeResult:
    """Computed clip representation."""

    strategy: ClipFallback
    custgeom: ClipCustGeom | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    used_bbox_rect: bool = False
    media: ClipMediaMeta | None = None
    xml_placeholder: str | None = None


def compute_clip_geometry(reference: ClipRef | MaskRef | MaskDefinition | None) -> ClipComputeResult | None:
    """Return a DrawingML-ready clip geometry for the provided reference."""

    if reference is None:
        return None

    definition = _resolve_definition(reference)

    segments: list[SegmentType] = []
    path_segments = getattr(reference, "path_segments", None)
    if not path_segments:
        path_segments = getattr(definition, "segments", None)
    if path_segments:
        segments.extend(path_segments)

    if not segments:
        segments.extend(segments_from_primitives(getattr(reference, "primitives", ())))
        segments.extend(segments_from_primitives(getattr(definition, "primitives", ())))

    if segments:
        result = _from_segments(reference, segments)
        if reference is not None and hasattr(reference, "clip_rule"):
            if result.custgeom is not None:
                result.custgeom.fill_rule_even_odd = str(getattr(reference, "clip_rule", "") or "").lower() == "evenodd"
        return result

    custom_xml = getattr(reference, "custom_geometry_xml", None)
    if custom_xml:
        bounds = getattr(reference, "custom_geometry_bounds", None)
        bbox_emu = rect_to_emu(bounds) if bounds is not None else (0, 0, 0, 0)
        return ClipComputeResult(
            strategy=ClipFallback.NONE,
            custgeom=ClipCustGeom(path=[], path_xml=custom_xml, bbox_emu=bbox_emu),
            metadata={"source": "custom_geometry_xml"},
            used_bbox_rect=False,
        )

    return None


def _from_segments(reference: ClipRef | MaskRef | MaskDefinition, segments: list[SegmentType]) -> ClipComputeResult | None:
    if not segments:
        return None

    clip_data = tessellate_segments(
        segments,
        generator=_CUST_GEOM_GENERATOR,
        closed=True,
    )

    metadata = {
        "source": "segments",
        "segment_count": len(segments),
    }
    if clip_data.bounds_px is not None:
        metadata["bounds_px"] = clip_data.bounds_px
    reference_id = getattr(reference, "clip_id", None) or getattr(reference, "mask_id", None)
    if reference_id is not None:
        metadata["reference_id"] = reference_id
        metadata.setdefault("clip_id", reference_id)

    return ClipComputeResult(
        strategy=ClipFallback.NONE,
        custgeom=ClipCustGeom(
            path=clip_data.segments,
            path_xml=clip_data.path_xml,
            bbox_emu=clip_data.bbox_emu,
        ),
        metadata=metadata,
        used_bbox_rect=True,
    )


def _resolve_definition(reference: ClipRef | MaskRef | MaskDefinition | None) -> MaskDefinition | None:
    if isinstance(reference, MaskRef):
        return reference.definition
    if isinstance(reference, ClipRef):
        return None
    if isinstance(reference, MaskDefinition):
        return reference
    return None
__all__ = [
    "ClipComputeResult",
    "ClipCustGeom",
    "ClipFallback",
    "ClipMediaMeta",
    "ClipPathSegment",
    "compute_clip_geometry",
]
