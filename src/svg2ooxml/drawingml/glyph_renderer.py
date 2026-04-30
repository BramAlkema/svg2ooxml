"""Render individual glyphs as custGeom shapes for per-character positioning."""

from __future__ import annotations

import math
from dataclasses import dataclass

from svg2ooxml.common.geometry.paths.quadratic import quadratic_tuple_to_cubic_controls
from svg2ooxml.drawingml.generator import px_to_emu
from svg2ooxml.ir.paint import SolidPaint, Stroke

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


@dataclass(frozen=True)
class PositionedGlyphBounds:
    """Rendered bounds for a positioned glyph outline."""

    char_index: int
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class _PositionedGlyphGeometry:
    char_index: int
    geometry_xml: str
    bbox: tuple[float, float, float, float]


def render_positioned_glyphs(
    text: str,
    font_family: str,
    font_size_pt: float,
    placements: list[GlyphPlacement],
    *,
    shape_id_start: int,
    fill_rgb: str = "000000",
    fill_opacity: float = 1.0,
    stroke_rgb: str | None = None,
    stroke_theme_color: str | None = None,
    stroke_width_px: float | None = None,
    stroke_opacity: float | None = None,
) -> tuple[str, int]:
    """Render each character as an individual custGeom shape.

    Returns (xml_fragments_joined, next_shape_id).
    """
    if not SKIA_AVAILABLE or not text or not placements:
        return "", shape_id_start

    fragments: list[str] = []
    sid = shape_id_start

    for glyph in _positioned_glyph_geometries(
        text,
        font_family,
        font_size_pt,
        placements,
    ):
        x, y, width, height = glyph.bbox
        x_emu = px_to_emu(x)
        y_emu = px_to_emu(y)
        w_emu = max(1, px_to_emu(width))
        h_emu = max(1, px_to_emu(height))

        opacity_attr = ""
        if fill_opacity < 1.0:
            from svg2ooxml.common.conversions.opacity import opacity_to_ppt

            alpha = opacity_to_ppt(fill_opacity)
            opacity_attr = f'<a:alpha val="{alpha}"/>'
        stroke_xml = _stroke_xml(
            stroke_rgb=stroke_rgb,
            stroke_theme_color=stroke_theme_color,
            stroke_width_px=stroke_width_px,
            stroke_opacity=stroke_opacity,
        )

        fragment = (
            f"<p:sp>"
            f"<p:nvSpPr>"
            f'<p:cNvPr id="{sid}" name="Glyph {sid}"/>'
            f'<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
            f"<p:nvPr/>"
            f"</p:nvSpPr>"
            f"<p:spPr>"
            f'<a:xfrm><a:off x="{x_emu}" y="{y_emu}"/>'
            f'<a:ext cx="{w_emu}" cy="{h_emu}"/></a:xfrm>'
            f"{glyph.geometry_xml}"
            f'<a:solidFill><a:srgbClr val="{fill_rgb.upper()}">'
            f"{opacity_attr}</a:srgbClr></a:solidFill>"
            f"{stroke_xml}"
            f"</p:spPr>"
            f"</p:sp>"
        )
        fragments.append(fragment)
        sid += 1

    return "".join(fragments), sid


def _stroke_xml(
    *,
    stroke_rgb: str | None,
    stroke_theme_color: str | None,
    stroke_width_px: float | None,
    stroke_opacity: float | None,
) -> str:
    if (
        (not stroke_rgb and not stroke_theme_color)
        or not stroke_width_px
        or stroke_width_px <= 0.0
    ):
        return ""

    from svg2ooxml.drawingml.paint_runtime import stroke_to_xml

    paint = SolidPaint(
        (stroke_rgb or "000000").upper(),
        opacity=1.0 if stroke_opacity is None else stroke_opacity,
        theme_color=stroke_theme_color,
    )
    return stroke_to_xml(Stroke(paint=paint, width=stroke_width_px))


def compute_positioned_glyph_bboxes(
    text: str,
    font_family: str,
    font_size_pt: float,
    placements: list[GlyphPlacement],
) -> list[PositionedGlyphBounds]:
    """Return the same glyph outline bboxes used by DrawingML emission."""
    return [
        PositionedGlyphBounds(char_index=glyph.char_index, bbox=glyph.bbox)
        for glyph in _positioned_glyph_geometries(
            text,
            font_family,
            font_size_pt,
            placements,
        )
    ]


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


def _positioned_glyph_geometries(
    text: str,
    font_family: str,
    font_size_pt: float,
    placements: list[GlyphPlacement],
) -> list[_PositionedGlyphGeometry]:
    if not SKIA_AVAILABLE or not text or not placements:
        return []

    font = _get_font(font_family, font_size_pt)
    glyphs = font.textToGlyphs(text)
    positioned: list[_PositionedGlyphGeometry] = []

    for index, (glyph_id, placement) in enumerate(
        zip(glyphs, placements, strict=False)
    ):
        if index >= len(text):
            break
        if text[index].isspace():
            continue

        path = font.getPath(int(glyph_id))
        if path is None or path.countVerbs() == 0:
            continue

        geometry_xml, bounds = _skia_path_to_custgeom(
            path,
            placement.rotation_deg,
        )
        if not geometry_xml:
            continue

        positioned.append(
            _PositionedGlyphGeometry(
                char_index=index,
                geometry_xml=geometry_xml,
                bbox=(
                    placement.x + bounds[0],
                    placement.y + bounds[1],
                    bounds[2],
                    bounds[3],
                ),
            )
        )

    return positioned


def _skia_path_to_custgeom(
    path,
    rotation_deg: float = 0.0,
) -> tuple[str, tuple[float, float, float, float]]:
    """Convert a Skia Path to DrawingML custGeom XML.

    Returns (xml_string, (offset_x, offset_y, width, height)).
    """
    bounds = path.getBounds()
    if bounds.width() <= 0 and bounds.height() <= 0:
        return "", (0, 0, 0, 0)

    ox, oy = bounds.fLeft, bounds.fTop
    source_w = max(bounds.width(), 0.01)
    source_h = max(bounds.height(), 0.01)
    segments = list(path)
    rotated_bounds = _rotated_path_bounds(
        segments,
        ox,
        oy,
        source_w,
        source_h,
        rotation_deg,
    )
    bx, by, w, h = rotated_bounds
    w_emu = max(1, px_to_emu(w))
    h_emu = max(1, px_to_emu(h))

    def point(pt) -> tuple[int, int]:
        return _transform_pt(
            pt,
            bx,
            by,
            w,
            h,
            w_emu,
            h_emu,
            rotation_deg,
        )

    # Build path commands
    commands: list[str] = []
    for verb, pts in segments:
        verb_name = str(verb).split(".")[-1]
        if verb_name == "kMove_Verb":
            x, y = point(pts[0])
            commands.append(f'<a:moveTo><a:pt x="{x}" y="{y}"/></a:moveTo>')
        elif verb_name == "kLine_Verb":
            x, y = point(pts[1])
            commands.append(f'<a:lnTo><a:pt x="{x}" y="{y}"/></a:lnTo>')
        elif verb_name == "kQuad_Verb":
            sx, sy = point(pts[0])
            qx, qy = point(pts[1])
            ex, ey = point(pts[2])
            c1, c2 = quadratic_tuple_to_cubic_controls(
                (sx, sy),
                (qx, qy),
                (ex, ey),
            )
            commands.append(
                f"<a:cubicBezTo>"
                f'<a:pt x="{int(round(c1[0]))}" y="{int(round(c1[1]))}"/>'
                f'<a:pt x="{int(round(c2[0]))}" y="{int(round(c2[1]))}"/>'
                f'<a:pt x="{ex}" y="{ey}"/>'
                f"</a:cubicBezTo>"
            )
        elif verb_name == "kCubic_Verb":
            c1x, c1y = point(pts[1])
            c2x, c2y = point(pts[2])
            ex, ey = point(pts[3])
            commands.append(
                f"<a:cubicBezTo>"
                f'<a:pt x="{c1x}" y="{c1y}"/>'
                f'<a:pt x="{c2x}" y="{c2y}"/>'
                f'<a:pt x="{ex}" y="{ey}"/>'
                f"</a:cubicBezTo>"
            )
        elif verb_name == "kClose_Verb":
            commands.append("<a:close/>")

    if not commands:
        return "", (0, 0, 0, 0)

    path_xml = "".join(commands)
    geom = (
        f"<a:custGeom>"
        f"<a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/>"
        f'<a:rect l="0" t="0" r="0" b="0"/>'
        f'<a:pathLst><a:path w="{w_emu}" h="{h_emu}">'
        f"{path_xml}"
        f"</a:path></a:pathLst>"
        f"</a:custGeom>"
    )
    return geom, rotated_bounds


def _transform_pt(
    pt,
    bx: float,
    by: float,
    w: float,
    h: float,
    w_emu: int,
    h_emu: int,
    rotation_deg: float,
) -> tuple[int, int]:
    """Transform a Skia point to custGeom coordinates inside expanded bounds."""
    px_x, px_y = _rotate_point(pt, 0.0, 0.0, rotation_deg)
    px_x -= bx
    px_y -= by

    emu_x = int(round(px_x / w * w_emu)) if w > 0 else 0
    emu_y = int(round(px_y / h * h_emu)) if h > 0 else 0
    return emu_x, emu_y


def _rotated_path_bounds(
    segments: list[tuple[object, object]],
    source_x: float,
    source_y: float,
    source_w: float,
    source_h: float,
    rotation_deg: float,
) -> tuple[float, float, float, float]:
    points = [
        _rotate_point(pt, 0.0, 0.0, rotation_deg)
        for _verb, pts in segments
        for pt in pts
    ]
    if not points:
        return source_x, source_y, source_w, source_h
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x = min(xs)
    min_y = min(ys)
    width = max(max(xs) - min_x, 0.01)
    height = max(max(ys) - min_y, 0.01)
    return min_x, min_y, width, height


def _rotate_point(
    pt,
    pivot_x: float,
    pivot_y: float,
    rotation_deg: float,
) -> tuple[float, float]:
    if not rotation_deg:
        return float(pt.x()), float(pt.y())
    rad = math.radians(rotation_deg)
    dx = float(pt.x()) - pivot_x
    dy = float(pt.y()) - pivot_y
    return (
        pivot_x + dx * math.cos(rad) - dy * math.sin(rad),
        pivot_y + dx * math.sin(rad) + dy * math.cos(rad),
    )
