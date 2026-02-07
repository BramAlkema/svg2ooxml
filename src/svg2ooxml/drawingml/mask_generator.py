"""Helpers for generating DrawingML geometry from mask definitions."""

from __future__ import annotations

from dataclasses import dataclass

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.common.geometry.paths.drawingml import PathCommand, build_path_commands
from svg2ooxml.drawingml.custgeom_generator import (
    CustGeomGenerationError,
    CustGeomGenerator,
    CustomGeometry,
    apply_matrix_to_segments,
    segments_from_primitives,
)
from svg2ooxml.ir.geometry import BezierSegment, LineSegment, SegmentType
from svg2ooxml.ir.scene import MaskDefinition, MaskRef


@dataclass(slots=True)
class MaskGeometryResult:
    """Computed mask geometry payload."""

    geometry: CustomGeometry | None
    segments: list[SegmentType]
    commands: list[PathCommand]
    diagnostics: list[str]


def _collect_segments(definition: MaskDefinition | None) -> list[SegmentType]:
    if definition is None:
        return []
    segments: list[SegmentType] = list(definition.segments or ())
    if not segments and definition.primitives:
        segments.extend(segments_from_primitives(definition.primitives))
    transform = getattr(definition, "transform", None)
    if transform:
        if isinstance(transform, Matrix2D):
            matrix = transform
        else:
            try:
                matrix = Matrix2D(*transform)
            except TypeError:
                matrix = None
        if matrix is not None:
            segments = apply_matrix_to_segments(segments, matrix)
    filtered: list[SegmentType] = []
    for segment in segments:
        if isinstance(segment, (LineSegment, BezierSegment)):
            filtered.append(segment)
    return filtered


def compute_mask_geometry(mask_ref: MaskRef | None) -> MaskGeometryResult | None:
    """Return mask geometry result for the provided reference."""

    if mask_ref is None or mask_ref.definition is None:
        return None

    definition = mask_ref.definition
    diagnostics: list[str] = []
    segments = _collect_segments(definition)
    if not segments:
        diagnostics.append(f"Mask {definition.mask_id} has no supported geometry.")
        return MaskGeometryResult(
            geometry=None,
            segments=[],
            commands=[],
            diagnostics=diagnostics,
        )

    generator = CustGeomGenerator()
    try:
        geometry = generator.generate_from_segments(
            segments,
            fill_mode="norm",
            stroke_mode="none",
            closed=True,
        )
    except CustGeomGenerationError as exc:
        diagnostics.append(f"Mask {definition.mask_id} geometry generation failed: {exc}")
        return MaskGeometryResult(
            geometry=None,
            segments=[],
            commands=[],
            diagnostics=diagnostics,
        )

    commands = build_path_commands(segments, closed=True)
    return MaskGeometryResult(
        geometry=geometry,
        segments=segments,
        commands=commands,
        diagnostics=diagnostics,
    )


__all__ = ["MaskGeometryResult", "compute_mask_geometry"]
