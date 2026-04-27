"""Render individual glyphs as custGeom shapes for per-character positioning."""

from __future__ import annotations

import math
from dataclasses import dataclass

from svg2ooxml.drawingml.generator import px_to_emu

try:
    import skia

    SKIA_AVAILABLE = True
except Exception:
    skia = None  # type: ignore
    SKIA_AVAILABLE = False

# Cache Skia Font objects by (family, size) — typeface creation is ~0.4ms each
_font_cache: dict[tuple[str, float], object] = {}


def _get_font(family: str, size_pt: float):
    """Get or create a cached Skia Font."""
    key = (family, size_pt)
    font = _font_cache.get(key)
    if font is None:
        typeface = skia.Typeface(family)
        font = skia.Font(typeface, size_pt)
        _font_cache[key] = font
    return font


@dataclass(frozen=True)
class GlyphPlacement:
    """Position and rotation for a single glyph."""

    x: float  # px
    y: float  # px
    rotation_deg: float = 0.0


def render_positioned_glyphs(
    text: str,
    font_family: str,
    font_size_pt: float,
    placements: list[GlyphPlacement],
    *,
    shape_id_start: int,
    fill_rgb: str = "000000",
    fill_opacity: float = 1.0,
) -> tuple[str, int]:
    """Render each character as an individual custGeom shape.

    Returns (xml_fragments_joined, next_shape_id).
    """
    if not SKIA_AVAILABLE or not text or not placements:
        return "", shape_id_start

    font = _get_font(font_family, font_size_pt)

    glyphs = font.textToGlyphs(text)
    fragments: list[str] = []
    sid = shape_id_start

    for i, (glyph_id, placement) in enumerate(zip(glyphs, placements, strict=False)):
        if i >= len(text):
            break
        char = text[i]
        if char.isspace():
            continue

        path = font.getPath(int(glyph_id))
        if path is None or path.countVerbs() == 0:
            continue

        geom_xml, bounds = _skia_path_to_custgeom(
            path, placement.rotation_deg,
        )
        if not geom_xml:
            continue

        # Position: placement coords + bounds offset
        x_emu = px_to_emu(placement.x + bounds[0])
        y_emu = px_to_emu(placement.y + bounds[1])
        w_emu = max(1, px_to_emu(bounds[2]))
        h_emu = max(1, px_to_emu(bounds[3]))

        opacity_attr = ""
        if fill_opacity < 1.0:
            from svg2ooxml.common.conversions.opacity import opacity_to_ppt

            alpha = opacity_to_ppt(fill_opacity)
            opacity_attr = f'<a:alpha val="{alpha}"/>'

        fragment = (
            f'<p:sp>'
            f'<p:nvSpPr>'
            f'<p:cNvPr id="{sid}" name="Glyph {sid}"/>'
            f'<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
            f'<p:nvPr/>'
            f'</p:nvSpPr>'
            f'<p:spPr>'
            f'<a:xfrm><a:off x="{x_emu}" y="{y_emu}"/>'
            f'<a:ext cx="{w_emu}" cy="{h_emu}"/></a:xfrm>'
            f'{geom_xml}'
            f'<a:solidFill><a:srgbClr val="{fill_rgb.upper()}">'
            f'{opacity_attr}</a:srgbClr></a:solidFill>'
            f'</p:spPr>'
            f'</p:sp>'
        )
        fragments.append(fragment)
        sid += 1

    return "".join(fragments), sid


def compute_glyph_placements(
    text: str,
    font_family: str,
    font_size_pt: float,
    origin_x: float,
    origin_y: float,
    *,
    dx: list[float] | None = None,
    dy: list[float] | None = None,
    abs_x: list[float] | None = None,
    abs_y: list[float] | None = None,
    rotate: list[float] | None = None,
) -> list[GlyphPlacement]:
    """Compute per-glyph positions from dx/dy, absolute x/y, and rotate arrays."""
    if not SKIA_AVAILABLE:
        return []

    font = _get_font(font_family, font_size_pt)
    glyphs = font.textToGlyphs(text)
    widths = font.getWidths(glyphs)

    placements: list[GlyphPlacement] = []
    cx, cy = origin_x, origin_y

    for i in range(len(text)):
        # Absolute position overrides
        if abs_x and i < len(abs_x):
            cx = abs_x[i]
        if abs_y and i < len(abs_y):
            cy = abs_y[i]

        # Relative offsets (cumulative)
        if dx and i < len(dx):
            cx += dx[i]
        if dy and i < len(dy):
            cy += dy[i]

        rot = 0.0
        if rotate:
            # SVG: last rotate value repeats for remaining chars
            rot = rotate[min(i, len(rotate) - 1)]

        placements.append(GlyphPlacement(x=cx, y=cy, rotation_deg=rot))

        # Advance cursor
        if i < len(widths):
            cx += widths[i]

    return placements


def _skia_path_to_custgeom(
    path, rotation_deg: float = 0.0,
) -> tuple[str, tuple[float, float, float, float]]:
    """Convert a Skia Path to DrawingML custGeom XML.

    Returns (xml_string, (offset_x, offset_y, width, height)).
    """
    bounds = path.getBounds()
    if bounds.width() <= 0 and bounds.height() <= 0:
        return "", (0, 0, 0, 0)

    ox, oy = bounds.fLeft, bounds.fTop
    w = max(bounds.width(), 0.01)
    h = max(bounds.height(), 0.01)
    w_emu = max(1, px_to_emu(w))
    h_emu = max(1, px_to_emu(h))

    # Build path commands
    commands: list[str] = []
    for verb, pts in iter(path):
        verb_name = str(verb).split(".")[-1]
        if verb_name == "kMove_Verb":
            x, y = _transform_pt(pts[0], ox, oy, w, h, w_emu, h_emu, rotation_deg)
            commands.append(f'<a:moveTo><a:pt x="{x}" y="{y}"/></a:moveTo>')
        elif verb_name == "kLine_Verb":
            x, y = _transform_pt(pts[1], ox, oy, w, h, w_emu, h_emu, rotation_deg)
            commands.append(f'<a:lnTo><a:pt x="{x}" y="{y}"/></a:lnTo>')
        elif verb_name == "kQuad_Verb":
            cx, cy = _transform_pt(pts[1], ox, oy, w, h, w_emu, h_emu, rotation_deg)
            ex, ey = _transform_pt(pts[2], ox, oy, w, h, w_emu, h_emu, rotation_deg)
            # Approximate quad bezier as cubic
            commands.append(
                f'<a:cubicBezTo>'
                f'<a:pt x="{cx}" y="{cy}"/>'
                f'<a:pt x="{cx}" y="{cy}"/>'
                f'<a:pt x="{ex}" y="{ey}"/>'
                f'</a:cubicBezTo>'
            )
        elif verb_name == "kCubic_Verb":
            c1x, c1y = _transform_pt(pts[1], ox, oy, w, h, w_emu, h_emu, rotation_deg)
            c2x, c2y = _transform_pt(pts[2], ox, oy, w, h, w_emu, h_emu, rotation_deg)
            ex, ey = _transform_pt(pts[3], ox, oy, w, h, w_emu, h_emu, rotation_deg)
            commands.append(
                f'<a:cubicBezTo>'
                f'<a:pt x="{c1x}" y="{c1y}"/>'
                f'<a:pt x="{c2x}" y="{c2y}"/>'
                f'<a:pt x="{ex}" y="{ey}"/>'
                f'</a:cubicBezTo>'
            )
        elif verb_name == "kClose_Verb":
            commands.append("<a:close/>")

    if not commands:
        return "", (0, 0, 0, 0)

    path_xml = "".join(commands)
    geom = (
        f'<a:custGeom>'
        f'<a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/>'
        f'<a:rect l="0" t="0" r="0" b="0"/>'
        f'<a:pathLst><a:path w="{w_emu}" h="{h_emu}">'
        f'{path_xml}'
        f'</a:path></a:pathLst>'
        f'</a:custGeom>'
    )
    return geom, (ox, oy, w, h)


def _transform_pt(
    pt, ox: float, oy: float,
    w: float, h: float,
    w_emu: int, h_emu: int,
    rotation_deg: float,
) -> tuple[int, int]:
    """Transform a Skia point to custGeom coordinates, optionally rotated."""
    px_x = pt.x() - ox
    px_y = pt.y() - oy

    if rotation_deg:
        # Rotate around center of glyph
        cx, cy = w / 2, h / 2
        rad = math.radians(rotation_deg)
        dx, dy = px_x - cx, px_y - cy
        px_x = cx + dx * math.cos(rad) - dy * math.sin(rad)
        px_y = cy + dx * math.sin(rad) + dy * math.cos(rad)

    emu_x = int(round(px_x / w * w_emu)) if w > 0 else 0
    emu_y = int(round(px_y / h * h_emu)) if h > 0 else 0
    return emu_x, emu_y
