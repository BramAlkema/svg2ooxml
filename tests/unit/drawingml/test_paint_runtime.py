from __future__ import annotations

from svg2ooxml.common.geometry import Matrix2D
from svg2ooxml.drawingml import paint_runtime
from svg2ooxml.drawingml.paint_runtime import _dash_elem, _pattern_to_fill_elem
from svg2ooxml.drawingml.xml_builder import to_string
from svg2ooxml.ir.geometry import Rect
from svg2ooxml.ir.paint import (
    GradientStop,
    LinearGradientPaint,
    PatternPaint,
    RadialGradientPaint,
    SolidPaint,
    Stroke,
)


def test_pattern_fill_uses_preset_and_colours() -> None:
    paint = PatternPaint(
        pattern_id="pat",
        preset="pct20",
        foreground="123456",
        background="abcdef",
    )

    xml = paint_runtime.paint_to_fill(paint)

    assert 'prst="pct20"' in xml
    assert 'val="123456"' in xml
    assert 'val="ABCDEF"' in xml


def test_solid_fill_prefers_scheme_color_when_theme_slot_present() -> None:
    paint = SolidPaint("4472C4", theme_color="accent1")

    xml = paint_runtime.paint_to_fill(paint)

    assert '<a:schemeClr val="accent1"/>' in xml
    assert 'val="4472C4"' not in xml


def test_solid_stroke_prefers_scheme_color_when_theme_slot_present() -> None:
    stroke = Stroke(paint=SolidPaint("ED7D31", theme_color="accent2"), width=2.0)

    xml = paint_runtime.stroke_to_xml(stroke)

    assert '<a:schemeClr val="accent2"/>' in xml
    assert 'val="ED7D31"' not in xml


def test_gradient_stops_support_theme_slots() -> None:
    paint = LinearGradientPaint(
        stops=[
            GradientStop(0.0, "4472C4", theme_color="accent1"),
            GradientStop(1.0, "ED7D31", opacity=0.5, theme_color="accent2"),
        ],
        start=(0.0, 0.0),
        end=(1.0, 0.0),
    )

    xml = paint_runtime.linear_gradient_to_fill(paint)

    assert '<a:schemeClr val="accent1"><a:alpha val="100000"/></a:schemeClr>' in xml
    assert '<a:schemeClr val="accent2"><a:alpha val="50000"/></a:schemeClr>' in xml
    assert 'val="4472C4"' not in xml
    assert 'val="ED7D31"' not in xml


def test_userspace_linear_gradient_is_projected_to_shape_bbox() -> None:
    paint = LinearGradientPaint(
        stops=[
            GradientStop(0.0, "FF0000"),
            GradientStop(1.0, "00FF00"),
        ],
        start=(10.0, 20.0),
        end=(110.0, 70.0),
        gradient_units="userSpaceOnUse",
    )
    bounds = Rect(x=10.0, y=20.0, width=100.0, height=50.0)

    xml = paint_runtime.paint_to_fill(paint, shape_bbox=bounds)

    assert 'ang="2700000"' in xml


def test_userspace_radial_gradient_is_projected_to_shape_bbox() -> None:
    paint = RadialGradientPaint(
        stops=[
            GradientStop(0.0, "FF0000"),
            GradientStop(1.0, "00FF00"),
        ],
        center=(60.0, 45.0),
        radius=25.0,
        gradient_units="userSpaceOnUse",
    )
    bounds = Rect(x=10.0, y=20.0, width=100.0, height=50.0)

    xml = paint_runtime.paint_to_fill(paint, shape_bbox=bounds)

    assert '<a:fillToRect l="25000" t="25000" r="25000" b="25000"/>' in xml


def test_pattern_fill_supports_theme_slots() -> None:
    paint = PatternPaint(
        pattern_id="pat_theme",
        preset="pct20",
        foreground="4472C4",
        background="FFFFFF",
        foreground_theme_color="accent1",
        background_theme_color="lt1",
    )

    xml = paint_runtime.paint_to_fill(paint)

    assert '<a:schemeClr val="accent1"/>' in xml
    assert '<a:schemeClr val="lt1"/>' in xml
    assert 'val="4472C4"' not in xml


def test_pattern_fill_supports_transparent_background() -> None:
    paint = PatternPaint(
        pattern_id="pat_transparent",
        preset="pct20",
        foreground="000000",
        background="FFFFFF",
        background_opacity=0.0,
    )

    xml = paint_runtime.paint_to_fill(paint)

    assert '<a:srgbClr val="FFFFFF"><a:alpha val="0"/></a:srgbClr>' in xml


def test_gradient_stroke_generates_gradient_fill() -> None:
    gradient = LinearGradientPaint(
        stops=[
            GradientStop(0.0, "FF0000"),
            GradientStop(1.0, "00FF00"),
        ],
        start=(0.0, 0.0),
        end=(1.0, 0.0),
    )
    stroke = Stroke(paint=gradient, width=2.0)

    xml = paint_runtime.stroke_to_xml(stroke)

    assert "<a:gradFill" in xml


def test_gradient_stroke_applies_stroke_opacity() -> None:
    gradient = LinearGradientPaint(
        stops=[
            GradientStop(0.0, "FF0000"),
            GradientStop(1.0, "00FF00"),
        ],
        start=(0.0, 0.0),
        end=(1.0, 0.0),
    )
    stroke = Stroke(paint=gradient, width=2.0, opacity=0.5)

    xml = paint_runtime.stroke_to_xml(stroke)

    assert xml.count('<a:alpha val="50000"/>') == 2


def test_dashed_stroke_emits_cust_dash() -> None:
    stroke = Stroke(
        paint=SolidPaint("000000"),
        width=1.0,
        dash_array=[4.0, 4.0],
    )

    xml = paint_runtime.stroke_to_xml(stroke)

    # custDash with ds elements: 4px on 1px width = 400000 (400%)
    assert "<a:custDash>" in xml
    assert '<a:ds d="400000" sp="400000"/>' in xml


def test_dashed_stroke_scales_by_stroke_width() -> None:
    stroke = Stroke(
        paint=SolidPaint("000000"),
        width=2.0,
        dash_array=[6.0, 3.0],
    )

    xml = paint_runtime.stroke_to_xml(stroke)

    # 6px on 2px width = 300000 (300%), 3px on 2px = 150000 (150%)
    assert '<a:ds d="300000" sp="150000"/>' in xml


def test_dashed_stroke_odd_array_is_doubled() -> None:
    stroke = Stroke(
        paint=SolidPaint("000000"),
        width=1.0,
        dash_array=[5.0, 3.0, 1.0],
    )

    xml = paint_runtime.stroke_to_xml(stroke)

    # SVG spec: [5,3,1] doubles to [5,3,1,5,3,1] => 3 ds pairs
    assert xml.count("<a:ds ") == 3


def test_dashed_stroke_complex_pattern() -> None:
    stroke = Stroke(
        paint=SolidPaint("000000"),
        width=2.0,
        dash_array=[10.0, 4.0, 2.0, 4.0],
    )

    xml = paint_runtime.stroke_to_xml(stroke)

    # 10/2=500%, 4/2=200%, 2/2=100%, 4/2=200%
    assert '<a:ds d="500000" sp="200000"/>' in xml
    assert '<a:ds d="100000" sp="200000"/>' in xml


def test_dash_ppt_compat_uses_absolute_units() -> None:
    """ppt_compat mode uses absolute hundredths-of-pt (matching PowerPoint behavior)."""
    elem = _dash_elem([4.0, 2.0], stroke_width=1.0, ppt_compat=True)
    xml = to_string(elem)

    # 4px * 75000 = 300000, 2px * 75000 = 150000
    assert '<a:ds d="300000" sp="150000"/>' in xml


def test_dash_ppt_compat_ignores_stroke_width() -> None:
    """ppt_compat values are absolute, not relative to stroke width."""
    # Same dash_array with different widths should produce same result in ppt_compat
    elem1 = _dash_elem([4.0, 2.0], stroke_width=1.0, ppt_compat=True)
    elem2 = _dash_elem([4.0, 2.0], stroke_width=3.0, ppt_compat=True)
    assert to_string(elem1) == to_string(elem2)


def test_dash_elem_normalizes_negative_and_nonfinite_values() -> None:
    elem = _dash_elem([-4.0, float("nan"), 2.0], stroke_width=1.0)
    xml = to_string(elem)

    assert '<a:ds d="400000" sp="200000"/>' in xml


def test_gradient_repeat_expands_stops() -> None:
    """spreadMethod=repeat duplicates stops to fill [0,1]."""
    paint = LinearGradientPaint(
        stops=[
            GradientStop(0.0, "FF0000"),
            GradientStop(0.5, "00FF00"),
        ],
        start=(0.0, 0.0),
        end=(1.0, 0.0),
        spread_method="repeat",
    )
    xml = paint_runtime.linear_gradient_to_fill(paint)
    # Should have more than 2 stops (expanded for repeat)
    assert xml.count("<a:gs ") >= 3


def test_gradient_reflect_mirrors_stops() -> None:
    """spreadMethod=reflect mirrors stops."""
    paint = LinearGradientPaint(
        stops=[
            GradientStop(0.0, "FF0000"),
            GradientStop(0.5, "00FF00"),
        ],
        start=(0.0, 0.0),
        end=(1.0, 0.0),
        spread_method="reflect",
    )
    xml = paint_runtime.linear_gradient_to_fill(paint)
    # Should have more stops than the original 2
    assert xml.count("<a:gs ") >= 3


def test_gradient_pad_keeps_original_stops() -> None:
    """spreadMethod=pad (default) keeps original stops unchanged."""
    paint = LinearGradientPaint(
        stops=[
            GradientStop(0.0, "FF0000"),
            GradientStop(1.0, "00FF00"),
        ],
        start=(0.0, 0.0),
        end=(1.0, 0.0),
        spread_method="pad",
    )
    xml = paint_runtime.linear_gradient_to_fill(paint)
    assert xml.count("<a:gs ") == 2


def test_gradient_no_spread_keeps_original_stops() -> None:
    """No spreadMethod keeps original stops unchanged."""
    paint = LinearGradientPaint(
        stops=[
            GradientStop(0.0, "FF0000"),
            GradientStop(1.0, "00FF00"),
        ],
        start=(0.0, 0.0),
        end=(1.0, 0.0),
    )
    xml = paint_runtime.linear_gradient_to_fill(paint)
    assert xml.count("<a:gs ") == 2


# ── Pattern tile blipFill tests ──────────────────────────────────────


def test_pattern_tile_generates_blip_fill() -> None:
    """PatternPaint with tile_relationship_id generates blipFill with tile mode."""
    paint = PatternPaint(
        pattern_id="pat1",
        tile_image=b"fake png",
        tile_width_px=8,
        tile_height_px=8,
        tile_relationship_id="rId5",
    )
    elem = _pattern_to_fill_elem(paint)
    xml = to_string(elem)

    assert "<a:blipFill" in xml
    assert 'r:embed="rId5"' in xml
    assert "<a:tile" in xml
    assert 'sx="100000"' in xml
    assert 'sy="100000"' in xml
    assert 'flip="none"' in xml
    assert 'algn="tl"' in xml


def test_pattern_tile_applies_simple_transform_to_tile_attrs() -> None:
    paint = PatternPaint(
        pattern_id="pat_transform",
        tile_image=b"fake png",
        tile_relationship_id="rId12",
        transform=(
            (2.0, 0.0, 0.25),
            (0.0, -0.5, -0.10),
            (0.0, 0.0, 1.0),
        ),
    )
    elem = _pattern_to_fill_elem(paint)
    xml = to_string(elem)

    assert "<a:tile" in xml
    assert 'sx="200000"' in xml
    assert 'sy="50000"' in xml
    assert 'tx="25000"' in xml
    assert 'ty="-10000"' in xml
    assert 'flip="y"' in xml


def test_pattern_tile_accepts_matrix2d_transform_to_tile_attrs() -> None:
    paint = PatternPaint(
        pattern_id="pat_matrix2d_transform",
        tile_image=b"fake png",
        tile_relationship_id="rId14",
        transform=Matrix2D.from_values(2.0, 0.0, 0.0, -0.5, 0.25, -0.10),
    )
    elem = _pattern_to_fill_elem(paint)
    xml = to_string(elem)

    assert "<a:tile" in xml
    assert 'sx="200000"' in xml
    assert 'sy="50000"' in xml
    assert 'tx="25000"' in xml
    assert 'ty="-10000"' in xml
    assert 'flip="y"' in xml


def test_pattern_tile_keeps_defaults_for_non_axis_aligned_transform() -> None:
    paint = PatternPaint(
        pattern_id="pat_transform_complex",
        tile_image=b"fake png",
        tile_relationship_id="rId13",
        transform=(
            (1.0, 0.2, 0.4),
            (0.1, 1.0, 0.3),
            (0.0, 0.0, 1.0),
        ),
    )
    elem = _pattern_to_fill_elem(paint)
    xml = to_string(elem)

    assert "<a:tile" in xml
    assert 'sx="100000"' in xml
    assert 'sy="100000"' in xml
    assert 'tx="0"' in xml
    assert 'ty="0"' in xml
    assert 'flip="none"' in xml


def test_pattern_tile_blip_fill_with_opacity() -> None:
    """Pattern tile blipFill applies opacity via alphaModFix."""
    paint = PatternPaint(
        pattern_id="pat2",
        tile_image=b"fake png",
        tile_relationship_id="rId7",
    )
    elem = _pattern_to_fill_elem(paint, opacity=0.5)
    xml = to_string(elem)

    assert "<a:blipFill" in xml
    assert "<a:alphaModFix" in xml


def test_pattern_tile_blip_fill_full_opacity_no_alpha() -> None:
    """Pattern tile blipFill omits alphaModFix at full opacity."""
    paint = PatternPaint(
        pattern_id="pat3",
        tile_image=b"fake png",
        tile_relationship_id="rId8",
    )
    elem = _pattern_to_fill_elem(paint, opacity=1.0)
    xml = to_string(elem)

    assert "<a:blipFill" in xml
    assert "alphaModFix" not in xml


def test_pattern_without_tile_uses_patt_fill() -> None:
    """PatternPaint without tile_relationship_id uses standard pattFill."""
    paint = PatternPaint(
        pattern_id="pat4",
        preset="horz",
        foreground="FF0000",
        background="FFFFFF",
    )
    elem = _pattern_to_fill_elem(paint)
    xml = to_string(elem)

    assert "<a:pattFill" in xml
    assert 'prst="horz"' in xml
    assert "blipFill" not in xml


def test_pattern_background_opacity_is_clamped_before_global_opacity() -> None:
    paint = PatternPaint(
        pattern_id="pat_opacity_clamp",
        preset="pct20",
        foreground="000000",
        background="FFFFFF",
        background_opacity=1.5,
    )
    elem = _pattern_to_fill_elem(paint, opacity=0.8)
    xml = to_string(elem)

    assert '<a:srgbClr val="FFFFFF"><a:alpha val="80000"/></a:srgbClr>' in xml


def test_pattern_tile_in_paint_to_fill() -> None:
    """paint_to_fill routes PatternPaint with tile to blipFill."""
    paint = PatternPaint(
        pattern_id="pat5",
        tile_image=b"fake png",
        tile_relationship_id="rId10",
    )
    xml = paint_runtime.paint_to_fill(paint)

    assert "<a:blipFill" in xml
    assert 'r:embed="rId10"' in xml


def test_pattern_tile_in_stroke() -> None:
    """stroke_to_xml handles PatternPaint with tile on stroke."""
    pattern = PatternPaint(
        pattern_id="pat6",
        tile_image=b"fake png",
        tile_relationship_id="rId11",
    )
    stroke = Stroke(paint=pattern, width=2.0)
    xml = paint_runtime.stroke_to_xml(stroke)

    assert "<a:ln" in xml
    assert "<a:blipFill" in xml
    assert 'r:embed="rId11"' in xml
