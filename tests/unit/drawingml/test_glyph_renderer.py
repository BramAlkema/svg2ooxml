"""Tests for positioned glyph outline rendering."""

from __future__ import annotations

import pytest

from svg2ooxml.drawingml.glyph_renderer import (
    SKIA_AVAILABLE,
    GlyphPlacement,
    compute_positioned_glyph_bboxes,
    render_positioned_glyphs,
)

pytestmark = pytest.mark.skipif(not SKIA_AVAILABLE, reason="skia-python not available")


def test_rotated_glyph_bbox_uses_rotated_outline_bounds() -> None:
    plain = compute_positioned_glyph_bboxes(
        "I",
        "Arial",
        48,
        [GlyphPlacement(100.0, 100.0, 0.0)],
    )[0]
    rotated = compute_positioned_glyph_bboxes(
        "I",
        "Arial",
        48,
        [GlyphPlacement(100.0, 100.0, 45.0)],
    )[0]

    plain_area = plain.bbox[2] * plain.bbox[3]
    rotated_area = rotated.bbox[2] * rotated.bbox[3]

    assert rotated_area > plain_area
    assert rotated.bbox != pytest.approx(plain.bbox)


def test_positioned_glyph_renderer_converts_point_size_to_svg_pixels() -> None:
    import skia

    font = skia.Font(skia.Typeface("Arial"), 35.0)
    glyph_id = font.textToGlyphs("H")[0]
    path = font.getPath(int(glyph_id))
    assert path is not None
    expected = path.getBounds()

    actual = compute_positioned_glyph_bboxes(
        "H",
        "Arial",
        26.25,
        [GlyphPlacement(0.0, 0.0, 0.0)],
    )[0]

    assert actual.bbox[2] == pytest.approx(expected.width(), rel=0.01)
    assert actual.bbox[3] == pytest.approx(expected.height(), rel=0.01)


def test_rotated_glyph_bbox_pivots_around_text_position() -> None:
    placement = GlyphPlacement(100.0, 100.0, 90.0)

    rotated = compute_positioned_glyph_bboxes(
        "I",
        "Arial",
        48,
        [placement],
    )[0]

    assert rotated.bbox[0] >= placement.x
    assert rotated.bbox[1] >= placement.y


def test_positioned_glyphs_emit_run_stroke() -> None:
    xml, next_id = render_positioned_glyphs(
        "A",
        "Arial",
        32,
        [GlyphPlacement(20.0, 60.0, 15.0)],
        shape_id_start=7,
        fill_rgb="00AA00",
        stroke_rgb="00FF00",
        stroke_width_px=0.5,
        stroke_opacity=0.5,
    )

    assert next_id == 8
    assert '<a:solidFill><a:srgbClr val="00AA00">' in xml
    assert '<a:ln w="' in xml
    assert '<a:srgbClr val="00FF00"><a:alpha val="50000"/>' in xml
