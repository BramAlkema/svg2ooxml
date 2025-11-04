"""Unit tests for drawingml.xml_builder module."""

import pytest
from lxml import etree

from svg2ooxml.drawingml.xml_builder import (
    a_elem,
    p_elem,
    a_sub,
    p_sub,
    to_string,
    solid_fill,
    srgb_color,
    no_fill,
    effect_list,
    ln,
    blur,
    glow,
    outer_shadow,
    soft_edge,
    NS_A,
    NS_P,
)


class TestCoreBuilders:
    """Test core element builders."""

    def test_a_elem_simple(self):
        """Test creating simple DrawingML element."""
        elem = a_elem("solidFill")
        assert elem.tag == f"{{{NS_A}}}solidFill"
        assert len(elem.attrib) == 0

    def test_a_elem_with_attributes(self):
        """Test creating element with attributes."""
        elem = a_elem("blur", rad="100000")
        assert elem.tag == f"{{{NS_A}}}blur"
        assert elem.get("rad") == "100000"

    def test_a_elem_with_multiple_attributes(self):
        """Test creating element with multiple attributes."""
        elem = a_elem("outerShdw", blurRad="100000", dist="50000", dir="2700000")
        assert elem.get("blurRad") == "100000"
        assert elem.get("dist") == "50000"
        assert elem.get("dir") == "2700000"

    def test_a_elem_converts_int_attributes(self):
        """Test that integer attributes are converted to strings."""
        elem = a_elem("blur", rad=100000)
        assert elem.get("rad") == "100000"
        assert isinstance(elem.get("rad"), str)

    def test_p_elem_simple(self):
        """Test creating simple PresentationML element."""
        elem = p_elem("txBody")
        assert elem.tag == f"{{{NS_P}}}txBody"
        assert len(elem.attrib) == 0

    def test_p_elem_with_attributes(self):
        """Test creating PresentationML element with attributes."""
        elem = p_elem("sp", id="1", name="Shape 1")
        assert elem.get("id") == "1"
        assert elem.get("name") == "Shape 1"

    def test_a_sub_creates_child(self):
        """Test creating child element with a_sub."""
        parent = a_elem("solidFill")
        child = a_sub(parent, "srgbClr", val="FF0000")

        assert len(parent) == 1
        assert parent[0] is child
        assert child.tag == f"{{{NS_A}}}srgbClr"
        assert child.get("val") == "FF0000"

    def test_a_sub_multiple_children(self):
        """Test creating multiple children with a_sub."""
        parent = a_elem("effectLst")
        child1 = a_sub(parent, "blur", rad="100000")
        child2 = a_sub(parent, "glow", rad="50000")

        assert len(parent) == 2
        assert parent[0] is child1
        assert parent[1] is child2

    def test_p_sub_creates_child(self):
        """Test creating child element with p_sub."""
        parent = p_elem("txBody")
        child = p_sub(parent, "bodyPr")

        assert len(parent) == 1
        assert parent[0] is child
        assert child.tag == f"{{{NS_P}}}bodyPr"


class TestToString:
    """Test XML serialization."""

    def test_to_string_simple_element(self):
        """Test serializing simple element."""
        elem = a_elem("noFill")
        xml = to_string(elem)
        assert xml == "<a:noFill/>"

    def test_to_string_element_with_attributes(self):
        """Test serializing element with attributes."""
        elem = a_elem("blur", rad="100000")
        xml = to_string(elem)
        assert xml == '<a:blur rad="100000"/>'

    def test_to_string_element_with_children(self):
        """Test serializing element with children."""
        parent = a_elem("solidFill")
        a_sub(parent, "srgbClr", val="FF0000")

        xml = to_string(parent)
        assert xml == '<a:solidFill><a:srgbClr val="FF0000"/></a:solidFill>'

    def test_to_string_nested_structure(self):
        """Test serializing deeply nested structure."""
        parent = a_elem("solidFill")
        child = a_sub(parent, "srgbClr", val="FF0000")
        a_sub(child, "alpha", val="50000")

        xml = to_string(parent)
        assert xml == '<a:solidFill><a:srgbClr val="FF0000"><a:alpha val="50000"/></a:srgbClr></a:solidFill>'

    def test_to_string_p_namespace(self):
        """Test serializing PresentationML element."""
        elem = p_elem("txBody")
        xml = to_string(elem)
        assert xml == "<p:txBody/>"

    def test_to_string_mixed_namespaces(self):
        """Test serializing mixed a: and p: namespaces."""
        parent = p_elem("txBody")
        a_sub(parent, "bodyPr")

        xml = to_string(parent)
        assert xml == "<p:txBody><a:bodyPr/></p:txBody>"

    def test_to_string_escapes_special_characters(self):
        """Test that lxml automatically escapes special characters."""
        elem = a_elem("latin", typeface="Rock & Roll")
        xml = to_string(elem)
        assert "Rock &amp; Roll" in xml

    def test_to_string_escapes_quotes_in_attributes(self):
        """Test that lxml escapes quotes in attributes."""
        elem = a_elem("latin", typeface='Font "Name"')
        xml = to_string(elem)
        # lxml uses single quotes when value contains double quotes
        assert "Font &quot;Name&quot;" in xml or "Font \"Name\"" in xml


class TestSolidFill:
    """Test solid_fill builder."""

    def test_solid_fill_opaque(self):
        """Test creating fully opaque solid fill."""
        fill = solid_fill("FF0000")
        xml = to_string(fill)

        assert xml == '<a:solidFill><a:srgbClr val="FF0000"/></a:solidFill>'

    def test_solid_fill_with_alpha(self):
        """Test creating solid fill with transparency."""
        fill = solid_fill("00FF00", alpha=50000)
        xml = to_string(fill)

        assert xml == '<a:solidFill><a:srgbClr val="00FF00"><a:alpha val="50000"/></a:srgbClr></a:solidFill>'

    def test_solid_fill_lowercase_color(self):
        """Test that lowercase hex colors are uppercased."""
        fill = solid_fill("ff0000")
        xml = to_string(fill)

        assert "FF0000" in xml
        assert "ff0000" not in xml

    def test_solid_fill_zero_alpha(self):
        """Test creating fully transparent solid fill."""
        fill = solid_fill("0000FF", alpha=0)
        xml = to_string(fill)

        assert '<a:alpha val="0"/>' in xml

    def test_solid_fill_partial_alpha(self):
        """Test creating partially transparent solid fill."""
        fill = solid_fill("FFFF00", alpha=75000)
        xml = to_string(fill)

        assert '<a:alpha val="75000"/>' in xml


class TestSrgbColor:
    """Test srgb_color builder."""

    def test_srgb_color_no_alpha(self):
        """Test creating sRGB color without alpha."""
        color = srgb_color("FF0000")
        xml = to_string(color)

        assert xml == '<a:srgbClr val="FF0000"/>'

    def test_srgb_color_with_alpha(self):
        """Test creating sRGB color with alpha."""
        color = srgb_color("00FF00", alpha=60000)
        xml = to_string(color)

        assert xml == '<a:srgbClr val="00FF00"><a:alpha val="60000"/></a:srgbClr>'

    def test_srgb_color_uppercase(self):
        """Test that color is uppercased."""
        color = srgb_color("abc123")
        xml = to_string(color)

        assert "ABC123" in xml


class TestNoFill:
    """Test no_fill builder."""

    def test_no_fill(self):
        """Test creating no fill element."""
        fill = no_fill()
        xml = to_string(fill)

        assert xml == "<a:noFill/>"


class TestEffectList:
    """Test effect_list builder."""

    def test_effect_list_empty(self):
        """Test creating empty effect list."""
        effects = effect_list()
        xml = to_string(effects)

        assert xml == "<a:effectLst/>"

    def test_effect_list_single_effect(self):
        """Test creating effect list with one effect."""
        blur_effect = a_elem("blur", rad="100000")
        effects = effect_list(blur_effect)
        xml = to_string(effects)

        assert xml == '<a:effectLst><a:blur rad="100000"/></a:effectLst>'

    def test_effect_list_multiple_effects(self):
        """Test creating effect list with multiple effects."""
        blur_effect = a_elem("blur", rad="100000")
        glow_effect = a_elem("glow", rad="50000")
        effects = effect_list(blur_effect, glow_effect)
        xml = to_string(effects)

        assert '<a:blur rad="100000"/>' in xml
        assert '<a:glow rad="50000"/>' in xml
        assert xml.startswith("<a:effectLst>")
        assert xml.endswith("</a:effectLst>")


class TestLn:
    """Test ln (line) builder."""

    def test_ln_no_fill(self):
        """Test creating line without fill."""
        line = ln(12700)
        xml = to_string(line)

        assert xml == '<a:ln w="12700"/>'

    def test_ln_with_solid_fill(self):
        """Test creating line with solid fill."""
        fill = solid_fill("000000")
        line = ln(12700, fill)
        xml = to_string(line)

        assert '<a:ln w="12700">' in xml
        assert '<a:solidFill>' in xml
        assert '</a:ln>' in xml

    def test_ln_with_no_fill_element(self):
        """Test creating line with no fill element."""
        fill = no_fill()
        line = ln(25400, fill)
        xml = to_string(line)

        assert '<a:ln w="25400"><a:noFill/></a:ln>' in xml

    def test_ln_with_attributes(self):
        """Test creating line with additional attributes."""
        line = ln(12700, cap="rnd", cmpd="sng")
        xml = to_string(line)

        assert 'w="12700"' in xml
        assert 'cap="rnd"' in xml
        assert 'cmpd="sng"' in xml


class TestBlur:
    """Test blur effect builder."""

    def test_blur(self):
        """Test creating blur effect."""
        blur_effect = blur(100000)
        xml = to_string(blur_effect)

        assert xml == '<a:blur rad="100000"/>'

    def test_blur_different_radius(self):
        """Test creating blur with different radius."""
        blur_effect = blur(50000)
        xml = to_string(blur_effect)

        assert xml == '<a:blur rad="50000"/>'


class TestGlow:
    """Test glow effect builder."""

    def test_glow_with_color(self):
        """Test creating glow effect with color."""
        color = srgb_color("FF0000", alpha=50000)
        glow_effect = glow(50000, color)
        xml = to_string(glow_effect)

        assert '<a:glow rad="50000">' in xml
        assert '<a:srgbClr val="FF0000">' in xml
        assert '<a:alpha val="50000"/>' in xml
        assert '</a:glow>' in xml

    def test_glow_different_radius(self):
        """Test creating glow with different radius."""
        color = srgb_color("00FF00")
        glow_effect = glow(100000, color)
        xml = to_string(glow_effect)

        assert 'rad="100000"' in xml


class TestOuterShadow:
    """Test outer_shadow builder."""

    def test_outer_shadow_basic(self):
        """Test creating basic outer shadow."""
        color = srgb_color("000000", alpha=50000)
        shadow = outer_shadow(100000, 50000, 2700000, color)
        xml = to_string(shadow)

        assert 'blurRad="100000"' in xml
        assert 'dist="50000"' in xml
        assert 'dir="2700000"' in xml
        assert '<a:srgbClr val="000000">' in xml

    def test_outer_shadow_with_extra_attrs(self):
        """Test creating outer shadow with additional attributes."""
        color = srgb_color("000000")
        shadow = outer_shadow(100000, 50000, 2700000, color, algn="ctr", rotWithShape="0")
        xml = to_string(shadow)

        assert 'algn="ctr"' in xml
        assert 'rotWithShape="0"' in xml


class TestSoftEdge:
    """Test soft_edge effect builder."""

    def test_soft_edge(self):
        """Test creating soft edge effect."""
        edge = soft_edge(25000)
        xml = to_string(edge)

        assert xml == '<a:softEdge rad="25000"/>'

    def test_soft_edge_different_radius(self):
        """Test creating soft edge with different radius."""
        edge = soft_edge(50000)
        xml = to_string(edge)

        assert xml == '<a:softEdge rad="50000"/>'


class TestIntegration:
    """Integration tests for complex structures."""

    def test_complex_nested_structure(self):
        """Test creating complex nested DrawingML structure."""
        # Create effect list with multiple effects
        blur_effect = blur(100000)
        color = srgb_color("FF0000", alpha=50000)
        glow_effect = glow(50000, color)
        effects = effect_list(blur_effect, glow_effect)

        xml = to_string(effects)

        assert xml.startswith("<a:effectLst>")
        assert '<a:blur rad="100000"/>' in xml
        assert '<a:glow rad="50000">' in xml
        assert '<a:srgbClr val="FF0000">' in xml
        assert '<a:alpha val="50000"/>' in xml
        assert xml.endswith("</a:effectLst>")

    def test_line_with_solid_fill_and_effects(self):
        """Test creating line with fill that could have effects."""
        fill = solid_fill("0000FF", alpha=75000)
        line = ln(12700, fill, cap="rnd")

        xml = to_string(line)

        assert '<a:ln' in xml
        assert 'w="12700"' in xml
        assert 'cap="rnd"' in xml
        assert '<a:solidFill>' in xml
        assert 'val="0000FF"' in xml
        assert '<a:alpha val="75000"/>' in xml

    def test_special_characters_in_attributes(self):
        """Test that special characters are properly escaped."""
        elem = a_elem("latin", typeface="Rock & Roll <Special>")
        xml = to_string(elem)

        assert "Rock &amp; Roll &lt;Special&gt;" in xml
        assert "&" not in xml.replace("&amp;", "").replace("&lt;", "").replace("&gt;", "")


__all__ = [
    "TestCoreBuilders",
    "TestToString",
    "TestSolidFill",
    "TestSrgbColor",
    "TestNoFill",
    "TestEffectList",
    "TestLn",
    "TestBlur",
    "TestGlow",
    "TestOuterShadow",
    "TestSoftEdge",
    "TestIntegration",
]
