"""Clip geometry computation utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List

from svg2ooxml.drawingml.custgeom_generator import CustGeomGenerator, segments_from_primitives
from svg2ooxml.geometry.paths.drawingml import PathCommand, build_path_commands
from svg2ooxml.ir.geometry import Rect, SegmentType
from svg2ooxml.ir.scene import ClipRef, MaskDefinition, MaskRef

EMU_PER_PX = 9525

_CUST_GEOM_GENERATOR = CustGeomGenerator()


class ClipFallback(Enum):
    """Fallback modes for clip emission."""

    NONE = "native"
    EMF_SHAPE = "emf_shape"
    EMF_GROUP = "emf_group"
    BITMAP = "bitmap"


@dataclass
class ClipCustGeom:
    """Custom geometry payload for clips."""

    path: List["ClipPathSegment"] = field(default_factory=list)
    path_xml: str | None = None
    fill_rule_even_odd: bool = False
    bbox_emu: tuple[int, int, int, int] | None = None


@dataclass
class ClipPathSegment:
    """Normalized path segment command."""

    cmd: str
    args: list[float] = field(default_factory=list)


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
        bbox_emu = _rect_to_emu(bounds) if bounds is not None else (0, 0, 0, 0)
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

    geometry = _CUST_GEOM_GENERATOR.generate_from_segments(segments, fill_mode="none", stroke_mode="none", closed=True)
    bbox = geometry.bounds
    commands = build_path_commands(segments, closed=True)
    path_xml = geometry.xml
    bbox_emu = _rect_to_emu(bbox)
    path_segments = _commands_to_segments(commands)

    metadata = {
        "source": "segments",
        "segment_count": len(segments),
        "bounds_px": (bbox.x, bbox.y, bbox.width, bbox.height),
    }
    reference_id = getattr(reference, "clip_id", None) or getattr(reference, "mask_id", None)
    if reference_id is not None:
        metadata["reference_id"] = reference_id
        metadata.setdefault("clip_id", reference_id)

    return ClipComputeResult(
        strategy=ClipFallback.NONE,
        custgeom=ClipCustGeom(path=path_segments, path_xml=path_xml, bbox_emu=bbox_emu),
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


def _commands_to_segments(commands: list[PathCommand]) -> list[ClipPathSegment]:
    segments: list[ClipPathSegment] = []
    for command in commands:
        args: list[float] = []
        if command.name in {"moveTo", "lnTo"}:
            if command.points:
                pt = command.points[0]
                args.extend([pt.x, pt.y])
        elif command.name == "cubicBezTo":
            for pt in command.points:
                args.extend([pt.x, pt.y])
        segments.append(ClipPathSegment(cmd=command.name, args=args))
    return segments


def _rect_to_emu(rect) -> tuple[int, int, int, int]:
    if rect is None:
        return (0, 0, 0, 0)
    return (
        _to_emu(rect.x),
        _to_emu(rect.y),
        _to_emu(rect.width),
        _to_emu(rect.height),
    )


def _to_emu(value: float) -> int:
    return int(round(value * EMU_PER_PX))


__all__ = [
    "ClipComputeResult",
    "ClipCustGeom",
    "ClipFallback",
    "compute_clip_geometry",
]
