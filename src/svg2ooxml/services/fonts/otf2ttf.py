"""Convert OTF (CFF outlines) to TTF (TrueType outlines) on the fly.

Microsoft Office requires TrueType outlines for font embedding. This module
converts CFF-based OpenType fonts to TrueType format using fontTools'
cubic-to-quadratic curve conversion.

Ported from tokenmoulds.fonts.otf2ttf.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import _g_l_y_f, _l_o_c_a

logger = logging.getLogger(__name__)

DEFAULT_MAX_ERR = 1.0
OPENTYPE_SUBSTITUTION_TABLES = ("GSUB",)
OPENTYPE_VARIATION_TABLES = (
    "fvar",
    "gvar",
    "avar",
    "HVAR",
    "MVAR",
    "VVAR",
    "STAT",
)
OPENTYPE_STRIP_TABLES = OPENTYPE_SUBSTITUTION_TABLES + OPENTYPE_VARIATION_TABLES


def _strip_opentype_tables(font: TTFont) -> None:
    for tag in OPENTYPE_STRIP_TABLES:
        if tag in font:
            del font[tag]


def _font_to_bytes(font: TTFont) -> bytes:
    output = io.BytesIO()
    font.save(output)
    return output.getvalue()


def _convert_cff_to_glyf(font: TTFont, max_err: float) -> TTFont:
    glyph_order = font.getGlyphOrder()
    glyph_set = font.getGlyphSet()

    glyf_table = _g_l_y_f.table__g_l_y_f()
    glyf_table.glyphs = {}
    glyf_table.glyphOrder = glyph_order

    converted = 0
    for name in glyph_order:
        tt_pen = TTGlyphPen(glyph_set)  # type: ignore[arg-type]
        cu2qu_pen = Cu2QuPen(tt_pen, max_err=max_err, reverse_direction=True)

        try:
            glyph_set[name].draw(cu2qu_pen)
            glyf_table[name] = tt_pen.glyph()
            converted += 1
        except Exception as exc:
            logger.warning("Failed to convert glyph '%s': %s", name, exc)
            glyf_table[name] = _g_l_y_f.Glyph()

    font["glyf"] = glyf_table
    font["loca"] = _l_o_c_a.table__l_o_c_a()

    for table in ("CFF ", "CFF2", "VORG"):
        if table in font:
            del font[table]

    maxp = font["maxp"]
    maxp.tableVersion = 0x00010000

    max_points = 0
    max_contours = 0
    max_component_elements = 0

    for name in glyph_order:
        glyph = glyf_table[name]
        if glyph.numberOfContours > 0:
            points = len(glyph.coordinates) if hasattr(glyph, "coordinates") else 0
            max_points = max(max_points, points)
            max_contours = max(max_contours, glyph.numberOfContours)
        elif glyph.numberOfContours == -1:
            if hasattr(glyph, "components"):
                max_component_elements = max(
                    max_component_elements, len(glyph.components)
                )

    maxp.maxPoints = max_points
    maxp.maxContours = max_contours
    maxp.maxCompositePoints = 0
    maxp.maxCompositeContours = 0
    maxp.maxZones = 2  # type: ignore[assignment]
    maxp.maxTwilightPoints = 0  # type: ignore[assignment]
    maxp.maxStorage = 0  # type: ignore[assignment]
    maxp.maxFunctionDefs = 0  # type: ignore[assignment]
    maxp.maxInstructionDefs = 0  # type: ignore[assignment]
    maxp.maxStackElements = 0  # type: ignore[assignment]
    maxp.maxSizeOfInstructions = 0  # type: ignore[assignment]
    maxp.maxComponentElements = max_component_elements
    maxp.maxComponentDepth = 0

    font["head"].glyphDataFormat = 0  # type: ignore[assignment]

    logger.info("Converted %d/%d glyphs to TrueType", converted, len(glyph_order))

    return font


def convert_font_bytes_for_embedding(
    font_bytes: bytes,
    *,
    strip_opentype_features: bool = False,
    max_err: float = DEFAULT_MAX_ERR,
) -> bytes:
    """Ensure font bytes carry TrueType outlines and optionally strip OT tables.

    If the bytes already describe a ``glyf``-flavoured font they are returned
    unchanged (unless ``strip_opentype_features`` is requested, in which case
    GSUB/variation tables are removed while GPOS kerning is preserved). If the
    bytes describe a CFF-flavoured font, glyphs are converted to TrueType
    outlines via ``Cu2QuPen``.
    """
    font = TTFont(io.BytesIO(font_bytes))

    try:
        if "glyf" in font:
            if strip_opentype_features:
                _strip_opentype_tables(font)
                return _font_to_bytes(font)
            return font_bytes

        if "CFF " in font or "CFF2" in font:
            font = _convert_cff_to_glyf(font, max_err)
            if strip_opentype_features:
                _strip_opentype_tables(font)
            return _font_to_bytes(font)

        raise ValueError("Unknown font format")
    finally:
        font.close()


def is_otf(font_path: str | Path) -> bool:
    """Return True if the font file uses CFF outlines."""
    font = TTFont(font_path)
    try:
        return "CFF " in font or "CFF2" in font
    finally:
        font.close()


def is_ttf(font_path: str | Path) -> bool:
    """Return True if the font file uses TrueType ``glyf`` outlines."""
    font = TTFont(font_path)
    try:
        return "glyf" in font
    finally:
        font.close()


def otf_to_ttf(
    otf_path: str | Path,
    max_err: float = DEFAULT_MAX_ERR,
) -> bytes:
    """Convert a CFF-based OpenType font to TrueType outlines.

    If the font is already TrueType, its bytes are re-serialised unchanged.
    Raises ``ValueError`` for non-CFF, non-glyf inputs.
    """
    font = TTFont(otf_path)
    try:
        if "glyf" in font:
            logger.debug("%s is already TTF, returning unchanged", otf_path)
            return _font_to_bytes(font)

        if "CFF " not in font and "CFF2" not in font:
            raise ValueError(f"{otf_path} is not a CFF-based font")

        logger.info("Converting %s from CFF to TrueType outlines", otf_path)
        font = _convert_cff_to_glyf(font, max_err)
        return _font_to_bytes(font)
    finally:
        font.close()


def convert_font_for_embedding(
    font_path: str | Path,
    *,
    strip_opentype_features: bool = False,
) -> bytes:
    """Load a font file and return TrueType bytes suitable for Office embedding."""
    font_path = Path(font_path)

    if not font_path.exists():
        raise FileNotFoundError(f"Font not found: {font_path}")

    if strip_opentype_features:
        font_bytes = font_path.read_bytes()
        return convert_font_bytes_for_embedding(
            font_bytes,
            strip_opentype_features=True,
        )

    font = TTFont(font_path)
    try:
        if "glyf" in font:
            return font_path.read_bytes()
        if "CFF " in font or "CFF2" in font:
            return otf_to_ttf(font_path)
        raise ValueError(f"Unknown font format: {font_path}")
    finally:
        font.close()


__all__ = [
    "DEFAULT_MAX_ERR",
    "convert_font_bytes_for_embedding",
    "convert_font_for_embedding",
    "is_otf",
    "is_ttf",
    "otf_to_ttf",
]
