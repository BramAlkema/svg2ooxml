"""Clip overlay builder — creates EMF frame with even-odd cutout."""

from __future__ import annotations

from collections.abc import Sequence

from svg2ooxml.drawingml.generator import EMU_PER_PX
from svg2ooxml.io.emf.blob import EMFBlob
from svg2ooxml.io.emf.path import flatten_segments
from svg2ooxml.ir.geometry import Rect, SegmentType


def build_clip_overlay_emf(
    bbox: Rect,
    clip_segments: Sequence[SegmentType],
    *,
    overlay_color: int = 0x00FFFFFF,
) -> bytes | None:
    """Build an EMF with a filled frame and an even-odd cutout for the clip path.

    The resulting EMF covers *bbox* with *overlay_color* everywhere **except**
    inside the *clip_segments* path, which is left transparent via the
    ALTERNATE (even-odd) polygon fill rule.

    Returns ``None`` if the clip path is degenerate or the bbox is too small.
    """
    if not clip_segments:
        return None
    if bbox.width <= 0 or bbox.height <= 0:
        return None

    width_emu = int(round(bbox.width * EMU_PER_PX))
    height_emu = int(round(bbox.height * EMU_PER_PX))
    if width_emu <= 0 or height_emu <= 0:
        return None

    # Flatten bezier clip path to polyline points (SVG user units).
    flat_points = flatten_segments(tuple(clip_segments))
    if len(flat_points) < 3:
        return None

    # Convert clip points: translate relative to bbox origin, scale to EMU.
    clip_emu: list[tuple[int, int]] = []
    for x, y in flat_points:
        ex = int(round((x - bbox.x) * EMU_PER_PX))
        ey = int(round((y - bbox.y) * EMU_PER_PX))
        clip_emu.append((ex, ey))

    # Outer rectangle contour (bbox boundary) in EMU.
    rect_emu: list[tuple[int, int]] = [
        (0, 0),
        (width_emu, 0),
        (width_emu, height_emu),
        (0, height_emu),
    ]

    blob = EMFBlob(width_emu, height_emu)
    blob.set_poly_fill_mode(1)  # ALTERNATE (even-odd)
    blob.fill_polypolygon(
        [rect_emu, clip_emu],
        brush_color=overlay_color,
    )
    return blob.finalize()
