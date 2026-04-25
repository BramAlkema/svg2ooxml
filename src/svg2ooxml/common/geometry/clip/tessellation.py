"""Utilities for turning clip primitives into path data and EMU bounds."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from svg2ooxml.common.geometry.paths.drawingml import PathCommand, build_path_commands
from svg2ooxml.common.units import px_to_emu
from svg2ooxml.common.units.scalars import EMU_PER_PX_AT_DEFAULT_DPI
from svg2ooxml.drawingml.custgeom_generator import CustGeomGenerator
from svg2ooxml.ir.geometry import SegmentType

EMU_PER_PX = int(EMU_PER_PX_AT_DEFAULT_DPI)


@dataclass(frozen=True)
class ClipPathSegment:
    """Normalized path segment command."""

    cmd: str
    args: list[float]


@dataclass(frozen=True)
class ClipPathData:
    """Tessellated clip payload."""

    path_xml: str
    bbox_emu: tuple[int, int, int, int]
    segments: list[ClipPathSegment]
    bounds_px: tuple[float, float, float, float] | None = None


def tessellate_segments(
    segments: Sequence[SegmentType],
    *,
    generator: CustGeomGenerator | None = None,
    closed: bool = True,
) -> ClipPathData:
    """Convert geometric segments into DrawingML path XML and EMU bounds."""

    if not segments:
        raise ValueError("segments must not be empty")

    geom_builder = generator or CustGeomGenerator()
    geometry = geom_builder.generate_from_segments(
        segments,
        fill_mode="none",
        stroke_mode="none",
        closed=closed,
    )

    commands = build_path_commands(list(segments), closed=closed)
    path_segments = commands_to_clip_segments(commands)
    bbox = getattr(geometry, "bounds", None)

    bbox_emu = rect_to_emu(bbox)
    bounds_px = None
    if bbox is not None:
        bounds_px = (bbox.x, bbox.y, bbox.width, bbox.height)

    return ClipPathData(
        path_xml=geometry.xml,
        bbox_emu=bbox_emu,
        segments=path_segments,
        bounds_px=bounds_px,
    )


def commands_to_clip_segments(commands: Iterable[PathCommand]) -> list[ClipPathSegment]:
    """Translate DrawingML path commands into clip segments."""

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


def rect_to_emu(rect) -> tuple[int, int, int, int]:
    """Convert a rectangle measured in px to EMUs."""

    if rect is None:
        return (0, 0, 0, 0)
    return (
        _to_emu(rect.x),
        _to_emu(rect.y),
        _to_emu(rect.width),
        _to_emu(rect.height),
    )


def _to_emu(value: float) -> int:
    return int(round(px_to_emu(value)))
