"""Tests for animation value formatters."""

from lxml import etree

from svg2ooxml.drawingml.animation.value_formatters import (
    format_angle_value,
    format_color_value,
    format_numeric_value,
    format_point_value,
)

NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _flt_val(elem: etree._Element) -> str | None:
    """Extract val from <p:val><p:fltVal val="..."/></p:val>."""
    flt = elem.find(f"{{{NS_P}}}fltVal")
    return flt.get("val") if flt is not None else None


class TestFormatNumericValue:
    """Test format_numeric_value formatter."""

    def test_basic_numeric(self):
        elem = format_numeric_value("100")
        assert elem.tag == f"{{{NS_P}}}val"
        assert _flt_val(elem) == "100"

    def test_large_number(self):
        elem = format_numeric_value("914400")
        assert _flt_val(elem) == "914400"

    def test_zero(self):
        elem = format_numeric_value("0")
        assert _flt_val(elem) == "0"

    def test_negative(self):
        elem = format_numeric_value("-100")
        assert _flt_val(elem) == "-100"

    def test_decimal(self):
        elem = format_numeric_value("123.456")
        assert _flt_val(elem) == "123.456"

    def test_returns_element(self):
        elem = format_numeric_value("100")
        assert isinstance(elem, etree._Element)

    def test_has_fltval_child(self):
        """Numeric values should have a <p:fltVal> child."""
        elem = format_numeric_value("100")
        assert len(elem) == 1
        assert elem[0].tag == f"{{{NS_P}}}fltVal"


class TestFormatColorValue:
    """Test format_color_value formatter."""

    def test_hex_color(self):
        elem = format_color_value("#FF0000")
        assert elem.tag == f"{{{NS_P}}}val"

        # Should have srgbClr descendant
        srgb = elem.find(f".//{{{NS_A}}}srgbClr")
        assert srgb is not None
        assert srgb.get("val") == "FF0000"

    def test_hex_without_hash(self):
        elem = format_color_value("00FF00")
        srgb = elem.find(f".//{{{NS_A}}}srgbClr")
        assert srgb.get("val") == "00FF00"

    def test_lowercase_hex(self):
        elem = format_color_value("#ff0000")
        srgb = elem.find(f".//{{{NS_A}}}srgbClr")
        # Should normalize to uppercase
        assert srgb.get("val") == "FF0000"

    def test_named_color(self):
        # Named colors should be converted to hex
        elem = format_color_value("red")
        srgb = elem.find(f".//{{{NS_A}}}srgbClr")
        assert srgb is not None
        # Should have some hex value (exact value depends on color_to_hex)
        assert len(srgb.get("val")) == 6

    def test_rgb_color(self):
        # RGB colors should be converted to hex
        elem = format_color_value("rgb(255, 0, 0)")
        srgb = elem.find(f".//{{{NS_A}}}srgbClr")
        assert srgb is not None
        assert len(srgb.get("val")) == 6

    def test_returns_element(self):
        elem = format_color_value("#FF0000")
        assert isinstance(elem, etree._Element)

    def test_has_clrval_with_srgbclr(self):
        """Color values should have <p:clrVal><a:srgbClr/></p:clrVal>."""
        elem = format_color_value("#FF0000")
        children = list(elem)
        assert len(children) == 1
        assert children[0].tag == f"{{{NS_P}}}clrVal"
        srgb = children[0].find(f"{{{NS_A}}}srgbClr")
        assert srgb is not None


class TestFormatPointValue:
    """Test format_point_value formatter."""

    def test_two_values(self):
        elem = format_point_value("1.5 2.0")
        assert elem.tag == f"{{{NS_P}}}val"

        # Should have pt child in NS_P
        pt = elem.find(f"{{{NS_P}}}pt")
        assert pt is not None
        assert pt.get("x") == "1.5"
        assert pt.get("y") == "2.0"

    def test_single_value_duplicated(self):
        """Single value should be duplicated to both x and y."""
        elem = format_point_value("2.0")
        pt = elem.find(f"{{{NS_P}}}pt")
        assert pt.get("x") == "2.0"
        assert pt.get("y") == "2.0"

    def test_comma_separated(self):
        elem = format_point_value("1.5,2.0")
        pt = elem.find(f"{{{NS_P}}}pt")
        assert pt.get("x") == "1.5"
        assert pt.get("y") == "2.0"

    def test_integer_values(self):
        elem = format_point_value("100 200")
        pt = elem.find(f"{{{NS_P}}}pt")
        assert pt.get("x") == "100.0"
        assert pt.get("y") == "200.0"

    def test_zero_values(self):
        elem = format_point_value("0 0")
        pt = elem.find(f"{{{NS_P}}}pt")
        assert pt.get("x") == "0.0"
        assert pt.get("y") == "0.0"

    def test_negative_values(self):
        elem = format_point_value("-1.5 2.0")
        pt = elem.find(f"{{{NS_P}}}pt")
        assert pt.get("x") == "-1.5"
        assert pt.get("y") == "2.0"

    def test_returns_element(self):
        elem = format_point_value("1.5 2.0")
        assert isinstance(elem, etree._Element)

    def test_has_pt_child(self):
        """Point values should have exactly one pt child."""
        elem = format_point_value("1.5 2.0")
        children = list(elem)
        assert len(children) == 1
        assert children[0].tag == f"{{{NS_P}}}pt"


class TestFormatAngleValue:
    """Test format_angle_value formatter."""

    def test_zero_degrees(self):
        elem = format_angle_value("0")
        assert elem.tag == f"{{{NS_P}}}val"
        assert _flt_val(elem) == "0"

    def test_common_angles(self):
        # 45 degrees = 2700000 (45 * 60000)
        elem = format_angle_value("45")
        assert _flt_val(elem) == "2700000"

        # 90 degrees = 5400000
        elem = format_angle_value("90")
        assert _flt_val(elem) == "5400000"

        # 180 degrees = 10800000
        elem = format_angle_value("180")
        assert _flt_val(elem) == "10800000"

        # 360 degrees = 21600000
        elem = format_angle_value("360")
        assert _flt_val(elem) == "21600000"

    def test_negative_angle(self):
        # -45 degrees = -2700000
        elem = format_angle_value("-45")
        assert _flt_val(elem) == "-2700000"

    def test_fractional_angle(self):
        # 45.5 degrees = 2730000
        elem = format_angle_value("45.5")
        assert _flt_val(elem) == "2730000"

    def test_returns_element(self):
        elem = format_angle_value("45")
        assert isinstance(elem, etree._Element)

    def test_has_fltval_child(self):
        """Angle values should have a <p:fltVal> child."""
        elem = format_angle_value("45")
        assert len(elem) == 1
        assert elem[0].tag == f"{{{NS_P}}}fltVal"


class TestFormatterCompatibility:
    """Test that formatters work with TAVBuilder."""

    def test_numeric_formatter_protocol(self):
        """Test that format_numeric_value matches ValueFormatter protocol."""
        # Should be callable with string and return Element
        elem = format_numeric_value("100")
        assert isinstance(elem, etree._Element)

    def test_color_formatter_protocol(self):
        """Test that format_color_value matches ValueFormatter protocol."""
        elem = format_color_value("#FF0000")
        assert isinstance(elem, etree._Element)

    def test_point_formatter_protocol(self):
        """Test that format_point_value matches ValueFormatter protocol."""
        elem = format_point_value("1.5 2.0")
        assert isinstance(elem, etree._Element)

    def test_angle_formatter_protocol(self):
        """Test that format_angle_value matches ValueFormatter protocol."""
        elem = format_angle_value("45")
        assert isinstance(elem, etree._Element)


class TestIntegration:
    """Test formatters in integrated workflows."""

    def test_numeric_animation_workflow(self):
        """Test numeric formatter in complete workflow."""
        # Simulate TAV builder usage
        values = ["0", "914400", "1828800"]
        elements = [format_numeric_value(v) for v in values]

        assert len(elements) == 3
        assert all(isinstance(e, etree._Element) for e in elements)
        assert _flt_val(elements[0]) == "0"
        assert _flt_val(elements[1]) == "914400"
        assert _flt_val(elements[2]) == "1828800"

    def test_color_animation_workflow(self):
        """Test color formatter in complete workflow."""
        # Simulate color animation
        colors = ["#FF0000", "#00FF00", "#0000FF"]
        elements = [format_color_value(c) for c in colors]

        assert len(elements) == 3

        # Each should have srgbClr descendant
        for elem in elements:
            srgb = elem.find(f".//{{{NS_A}}}srgbClr")
            assert srgb is not None

    def test_scale_animation_workflow(self):
        """Test point formatter for scale animation."""
        # Simulate scale animation (1.0 → 1.5 → 2.0)
        scales = ["1.0", "1.5", "2.0"]
        elements = [format_point_value(s) for s in scales]

        assert len(elements) == 3

        # Check scale values (pt now in NS_P)
        pts = [e.find(f"{{{NS_P}}}pt") for e in elements]
        assert pts[0].get("x") == "1.0"
        assert pts[1].get("x") == "1.5"
        assert pts[2].get("x") == "2.0"

    def test_rotation_animation_workflow(self):
        """Test angle formatter for rotation animation."""
        # Simulate rotation (0° → 90° → 180° → 360°)
        angles = ["0", "90", "180", "360"]
        elements = [format_angle_value(a) for a in angles]

        assert len(elements) == 4
        assert _flt_val(elements[0]) == "0"
        assert _flt_val(elements[1]) == "5400000"
        assert _flt_val(elements[2]) == "10800000"
        assert _flt_val(elements[3]) == "21600000"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_string_numeric(self):
        """Empty string should still produce element."""
        elem = format_numeric_value("")
        assert isinstance(elem, etree._Element)

    def test_empty_string_color(self):
        """Empty color should use default."""
        elem = format_color_value("")
        srgb = elem.find(f".//{{{NS_A}}}srgbClr")
        assert srgb is not None  # Should have default color

    def test_empty_string_point(self):
        """Empty point should default to (0, 0) or (1, 1)."""
        elem = format_point_value("")
        pt = elem.find(f"{{{NS_P}}}pt")
        assert pt is not None

    def test_empty_string_angle(self):
        """Empty angle should default to 0."""
        elem = format_angle_value("")
        assert _flt_val(elem) == "0"

    def test_whitespace_numeric(self):
        elem = format_numeric_value("  100  ")
        # Should handle whitespace gracefully
        assert isinstance(elem, etree._Element)

    def test_very_large_number(self):
        elem = format_numeric_value("99999999")
        assert _flt_val(elem) == "99999999"

    def test_scientific_notation_angle(self):
        elem = format_angle_value("4.5e1")  # 45 in scientific notation
        assert _flt_val(elem) == "2700000"
