"""Tests for animation XML builders."""

import pytest
from lxml import etree

from svg2ooxml.drawingml.animation.xml_builders import AnimationXMLBuilder
from svg2ooxml.drawingml.xml_builder import NS_A
from svg2ooxml.drawingml.animation.constants import SVG2_ANIMATION_NS


def _parse_animation_fragment(fragment: str) -> etree._Element:
    """Parse animation XML fragment with DrawingML namespace."""
    wrapped = f'<root xmlns:a="{NS_A}">{fragment}</root>'
    root = etree.fromstring(wrapped)
    return root[0] if len(root) > 0 else root


class TestBehaviorCore:
    """Test build_behavior_core method."""

    def test_basic_behavior(self):
        builder = AnimationXMLBuilder()

        bhvr_xml = builder.build_behavior_core(
            behavior_id=1002,
            duration_ms=1000,
            target_shape="shape1"
        )
        bhvr = _parse_animation_fragment(bhvr_xml)

        assert bhvr.tag.endswith("cBhvr")

        # Find cTn child
        cTn = bhvr.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}cTn")
        assert cTn is not None
        assert cTn.get("id") == "1002"
        assert cTn.get("dur") == "1000"
        assert cTn.get("fill") == "hold"

    def test_behavior_with_repeat(self):
        builder = AnimationXMLBuilder()

        bhvr_xml = builder.build_behavior_core(
            behavior_id=1002,
            duration_ms=1000,
            target_shape="shape1",
            repeat_count="indefinite"
        )
        bhvr = _parse_animation_fragment(bhvr_xml)

        cTn = bhvr.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}cTn")
        assert cTn.get("repeatCount") == "indefinite"

    def test_behavior_with_accel_decel(self):
        builder = AnimationXMLBuilder()

        bhvr_xml = builder.build_behavior_core(
            behavior_id=1002,
            duration_ms=1000,
            target_shape="shape1",
            accel=50000,
            decel=50000
        )
        bhvr = _parse_animation_fragment(bhvr_xml)

        cTn = bhvr.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}cTn")
        assert cTn.get("accel") == "50000"
        assert cTn.get("decel") == "50000"

    def test_behavior_target_element(self):
        builder = AnimationXMLBuilder()

        bhvr_xml = builder.build_behavior_core(
            behavior_id=1002,
            duration_ms=1000,
            target_shape="shape1"
        )
        bhvr = _parse_animation_fragment(bhvr_xml)

        # Find spTgt
        spTgt = bhvr.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}spTgt")
        assert spTgt is not None
        assert spTgt.get("spid") == "shape1"


class TestAttributeList:
    """Test build_attribute_list method."""

    def test_single_attribute(self):
        builder = AnimationXMLBuilder()

        attr_list = builder.build_attribute_list(["ppt_x"])

        assert attr_list.tag.endswith("attrNameLst")

        # Find attrName children
        attr_names = attr_list.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}attrName")
        assert len(attr_names) == 1
        assert attr_names[0].get("val") == "ppt_x"
        assert attr_names[0].get("type") is None

    def test_multiple_attributes(self):
        builder = AnimationXMLBuilder()

        attr_list = builder.build_attribute_list(["ppt_x", "ppt_y", "ppt_w"])

        attr_names = attr_list.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}attrName")
        assert len(attr_names) == 3

        values = [attr.get("val") for attr in attr_names]
        assert values == ["ppt_x", "ppt_y", "ppt_w"]

    def test_empty_attribute_list(self):
        builder = AnimationXMLBuilder()

        attr_list = builder.build_attribute_list([])

        attr_names = attr_list.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}attrName")
        assert len(attr_names) == 0


class TestTAVElement:
    """Test build_tav_element method."""

    def test_basic_tav(self):
        builder = AnimationXMLBuilder()

        val = builder.build_numeric_value("100")
        tav = builder.build_tav_element(
            tm=0,
            value_elem=val,
            accel=0,
            decel=0
        )

        assert tav.tag.endswith("tav")
        assert tav.get("tm") == "0"

        # Check value child
        val_child = tav.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}val")
        assert val_child is not None

    def test_tav_with_accel_decel(self):
        builder = AnimationXMLBuilder()

        val = builder.build_numeric_value("100")
        tav = builder.build_tav_element(
            tm=50000,
            value_elem=val,
            accel=25000,
            decel=25000
        )

        assert tav.get("tm") == "50000"

        # Check accel/decel children
        accel_elem = tav.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}accel")
        decel_elem = tav.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}decel")

        assert accel_elem is not None
        assert accel_elem.get("val") == "25000"
        assert decel_elem is not None
        assert decel_elem.get("val") == "25000"

    def test_tav_with_metadata(self):
        builder = AnimationXMLBuilder()

        val = builder.build_numeric_value("100")
        tav = builder.build_tav_element(
            tm=0,
            value_elem=val,
            accel=0,
            decel=0,
            metadata={"svg2:spline": "0.42 0 0.58 1"}
        )

        # Check for custom namespace attribute
        spline_attr = tav.get(f"{{{SVG2_ANIMATION_NS}}}spline")
        assert spline_attr == "0.42 0 0.58 1"

    def test_tav_zero_accel_decel_not_added(self):
        builder = AnimationXMLBuilder()

        val = builder.build_numeric_value("100")
        tav = builder.build_tav_element(
            tm=0,
            value_elem=val,
            accel=0,
            decel=0
        )

        # Zero accel/decel should not create child elements
        accel_elem = tav.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}accel")
        decel_elem = tav.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}decel")

        assert accel_elem is None
        assert decel_elem is None


class TestStartCondition:
    """Test build_start_condition method."""

    def test_basic_start_condition(self):
        builder = AnimationXMLBuilder()

        cond = builder.build_start_condition(1000)

        assert cond.tag.endswith("cond")
        assert cond.get("delay") == "1000"

    def test_zero_delay(self):
        builder = AnimationXMLBuilder()

        cond = builder.build_start_condition(0)

        assert cond.get("delay") == "0"


class TestTAVListContainer:
    """Test build_tav_list_container method."""

    def test_empty_tav_list(self):
        builder = AnimationXMLBuilder()

        tavLst = builder.build_tav_list_container([])

        assert tavLst.tag.endswith("tavLst")
        assert len(tavLst) == 0

    def test_multiple_tavs(self):
        builder = AnimationXMLBuilder()

        val1 = builder.build_numeric_value("0")
        val2 = builder.build_numeric_value("100")

        tav1 = builder.build_tav_element(tm=0, value_elem=val1)
        tav2 = builder.build_tav_element(tm=100000, value_elem=val2)

        tavLst = builder.build_tav_list_container([tav1, tav2])

        assert len(tavLst) == 2

        tavs = tavLst.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}tav")
        assert len(tavs) == 2


class TestValueElements:
    """Test value element builders."""

    def test_numeric_value(self):
        builder = AnimationXMLBuilder()

        val = builder.build_numeric_value("12345")

        assert val.tag.endswith("val")
        assert val.get("val") == "12345"

    def test_color_value(self):
        builder = AnimationXMLBuilder()

        val = builder.build_color_value("FF0000")

        assert val.tag.endswith("val")

        # Check srgbClr child
        srgb = val.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}srgbClr")
        assert srgb is not None
        assert srgb.get("val") == "FF0000"

    def test_point_value(self):
        builder = AnimationXMLBuilder()

        val = builder.build_point_value("100", "200")

        assert val.tag.endswith("val")

        # Check pt child
        pt = val.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}pt")
        assert pt is not None
        assert pt.get("x") == "100"
        assert pt.get("y") == "200"


class TestParContainer:
    """Test build_par_container method."""

    def test_basic_par(self):
        builder = AnimationXMLBuilder()

        # Create simple child content
        child = "<a:anim xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'></a:anim>"

        par_xml = builder.build_par_container(
            par_id=1001,
            duration_ms=1000,
            delay_ms=0,
            child_content=child
        )

        assert "<p:par>" in par_xml
        assert 'id="1001"' in par_xml

    def test_par_with_delay(self):
        builder = AnimationXMLBuilder()

        child = "<a:anim xmlns:a='http://schemas.openxmlformats.org/drawingml/2006/main'></a:anim>"

        par_xml = builder.build_par_container(
            par_id=1001,
            duration_ms=1000,
            delay_ms=500,
            child_content=child
        )

        assert "<p:stCondLst>" in par_xml
        assert 'delay="500"' in par_xml

    def test_par_with_malformed_child(self):
        builder = AnimationXMLBuilder()

        # Malformed XML
        child = "<invalid><unclosed>"

        par_xml = builder.build_par_container(
            par_id=1001,
            duration_ms=1000,
            delay_ms=0,
            child_content=child
        )

        # Should still produce valid par (without child)
        assert "<p:par>" in par_xml


class TestTimingContainer:
    """Test build_timing_container method."""

    def test_basic_timing(self):
        builder = AnimationXMLBuilder()

        # Create simple fragment
        fragment = "<p:par xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main'></p:par>"

        timing_xml = builder.build_timing_container(
            timing_id=1,
            fragments=[fragment]
        )

        assert "<p:timing>" in timing_xml
        assert 'id="1"' in timing_xml
        assert 'nodeType="tmRoot"' in timing_xml

    def test_multiple_fragments(self):
        builder = AnimationXMLBuilder()

        fragments = [
            "<p:par xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main'></p:par>",
            "<p:par xmlns:p='http://schemas.openxmlformats.org/presentationml/2006/main'></p:par>",
        ]

        timing_xml = builder.build_timing_container(
            timing_id=1,
            fragments=fragments
        )

        # Should contain both fragments (as <p:par/> inside childTnLst)
        # One outer <p:par> container, two inner fragments
        assert "<p:childTnLst>" in timing_xml
        assert timing_xml.count("<p:par/>") == 2  # The two fragments

    def test_empty_fragments(self):
        builder = AnimationXMLBuilder()

        timing_xml = builder.build_timing_container(
            timing_id=1,
            fragments=[]
        )

        assert "<p:timing>" in timing_xml


class TestIntegration:
    """Test integrated workflows."""

    def test_complete_animation_structure(self):
        """Test building a complete animation structure."""
        builder = AnimationXMLBuilder()

        # 1. Build TAV elements
        val1 = builder.build_numeric_value("0")
        val2 = builder.build_numeric_value("100")

        tav1 = builder.build_tav_element(tm=0, value_elem=val1)
        tav2 = builder.build_tav_element(tm=100000, value_elem=val2)

        # 2. Build TAV list
        tavLst = builder.build_tav_list_container([tav1, tav2])

        # 3. Build behavior
        bhvr = builder.build_behavior_core(
            behavior_id=1002,
            duration_ms=1000,
            target_shape="shape1"
        )

        # All elements should be valid
        assert tavLst is not None
        assert bhvr is not None

    def test_namespace_handling(self):
        """Test that custom namespaces are properly handled."""
        builder = AnimationXMLBuilder()

        val = builder.build_numeric_value("100")
        tav = builder.build_tav_element(
            tm=0,
            value_elem=val,
            metadata={
                "svg2:spline": "0.42 0 0.58 1",
                "svg2:custom": "test"
            }
        )

        # Verify custom namespace attributes
        assert tav.get(f"{{{SVG2_ANIMATION_NS}}}spline") == "0.42 0 0.58 1"
        assert tav.get(f"{{{SVG2_ANIMATION_NS}}}custom") == "test"
