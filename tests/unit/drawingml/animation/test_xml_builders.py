"""Tests for animation XML builders."""

from lxml import etree

from svg2ooxml.drawingml.animation.constants import SVG2_ANIMATION_NS
from svg2ooxml.drawingml.animation.id_allocator import TimingIDAllocator
from svg2ooxml.drawingml.animation.xml_builders import AnimationXMLBuilder
from svg2ooxml.drawingml.xml_builder import NS_P


class TestAttributeList:
    """Test build_attribute_list method."""

    def test_single_attribute(self):
        builder = AnimationXMLBuilder()

        attr_list = builder.build_attribute_list(["ppt_x"])

        assert attr_list.tag.endswith("attrNameLst")

        # Find attrName children (in p: namespace)
        attr_names = attr_list.findall(".//{http://schemas.openxmlformats.org/presentationml/2006/main}attrName")
        assert len(attr_names) == 1
        assert attr_names[0].text == "ppt_x"

    def test_multiple_attributes(self):
        builder = AnimationXMLBuilder()

        attr_list = builder.build_attribute_list(["ppt_x", "ppt_y", "ppt_w"])

        attr_names = attr_list.findall(".//{http://schemas.openxmlformats.org/presentationml/2006/main}attrName")
        assert len(attr_names) == 3

        values = [attr.text for attr in attr_names]
        assert values == ["ppt_x", "ppt_y", "ppt_w"]

    def test_empty_attribute_list(self):
        builder = AnimationXMLBuilder()

        attr_list = builder.build_attribute_list([])

        attr_names = attr_list.findall(".//{http://schemas.openxmlformats.org/presentationml/2006/main}attrName")
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

        # Check value child (in p: namespace)
        val_child = tav.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}val")
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

        # Check accel/decel attributes on tavPr (in p: namespace)
        tav_pr = tav.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}tavPr")
        assert tav_pr is not None
        assert tav_pr.get("accel") == "25000"
        assert tav_pr.get("decel") == "25000"

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

        # Zero accel/decel should not create tavPr (in p: namespace)
        tav_pr = tav.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}tavPr")
        assert tav_pr is None


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

        tavs = tavLst.findall(".//{http://schemas.openxmlformats.org/presentationml/2006/main}tav")
        assert len(tavs) == 2


class TestValueElements:
    """Test value element builders."""

    def test_numeric_value(self):
        builder = AnimationXMLBuilder()

        val = builder.build_numeric_value("12345")

        assert val.tag.endswith("val")

        # Check fltVal child
        flt_val = val.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}fltVal")
        assert flt_val is not None
        assert flt_val.get("val") == "12345"

    def test_color_value(self):
        builder = AnimationXMLBuilder()

        val = builder.build_color_value("FF0000")

        assert val.tag.endswith("val")

        # Check srgbClr child (in p: namespace)
        srgb = val.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}srgbClr")
        assert srgb is not None
        assert srgb.get("val") == "FF0000"

    def test_point_value(self):
        builder = AnimationXMLBuilder()

        val = builder.build_point_value("100", "200")

        assert val.tag.endswith("val")

        # Check pt child (in p: namespace)
        pt = val.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}pt")
        assert pt is not None
        assert pt.get("x") == "100"
        assert pt.get("y") == "200"


class TestBuildTimingTree:
    """Test build_timing_tree — ECMA-376 compliant structure."""

    def _make_dummy_par(self) -> etree._Element:
        """Create a minimal <p:par> element for testing."""
        from svg2ooxml.drawingml.xml_builder import p_elem as _p
        return _p("par")

    def test_returns_element(self):
        builder = AnimationXMLBuilder()
        ids = TimingIDAllocator().allocate(1)
        tree = builder.build_timing_tree(
            ids=ids,
            animation_elements=[self._make_dummy_par()],
            animated_shape_ids=[],
        )
        assert isinstance(tree, etree._Element)
        assert tree.tag == f"{{{NS_P}}}timing"

    def test_root_ids(self):
        builder = AnimationXMLBuilder()
        ids = TimingIDAllocator().allocate(1)
        tree = builder.build_timing_tree(
            ids=ids,
            animation_elements=[self._make_dummy_par()],
            animated_shape_ids=[],
        )
        # tmRoot cTn
        root_ctn = tree.find(f".//{{{NS_P}}}cTn[@nodeType='tmRoot']")
        assert root_ctn is not None
        assert root_ctn.get("id") == "1"
        assert root_ctn.get("dur") == "indefinite"
        assert root_ctn.get("restart") == "never"

    def test_main_seq_id(self):
        builder = AnimationXMLBuilder()
        ids = TimingIDAllocator().allocate(1)
        tree = builder.build_timing_tree(
            ids=ids,
            animation_elements=[self._make_dummy_par()],
            animated_shape_ids=[],
        )
        seq_ctn = tree.find(f".//{{{NS_P}}}cTn[@nodeType='mainSeq']")
        assert seq_ctn is not None
        assert seq_ctn.get("id") == "2"

    def test_click_group_present(self):
        builder = AnimationXMLBuilder()
        ids = TimingIDAllocator().allocate(2)
        elems = [self._make_dummy_par(), self._make_dummy_par()]
        tree = builder.build_timing_tree(
            ids=ids,
            animation_elements=elems,
            animated_shape_ids=[],
        )
        # Click group is a par > cTn with id=3
        click_ctn = tree.find(f".//{{{NS_P}}}cTn[@id='3']")
        assert click_ctn is not None
        assert click_ctn.get("fill") == "hold"

        # Animations are children of the click group's childTnLst
        click_child_lst = click_ctn.find(f"{{{NS_P}}}childTnLst")
        assert click_child_lst is not None
        assert len(click_child_lst) == 2

    def test_navigation_triggers(self):
        builder = AnimationXMLBuilder()
        ids = TimingIDAllocator().allocate(0)
        tree = builder.build_timing_tree(
            ids=ids,
            animation_elements=[],
            animated_shape_ids=[],
        )
        seq = tree.find(f".//{{{NS_P}}}seq")
        prev = seq.find(f"{{{NS_P}}}prevCondLst")
        next_ = seq.find(f"{{{NS_P}}}nextCondLst")
        assert prev is not None
        assert next_ is not None

    def test_bld_lst(self):
        builder = AnimationXMLBuilder()
        ids = TimingIDAllocator().allocate(1)
        tree = builder.build_timing_tree(
            ids=ids,
            animation_elements=[self._make_dummy_par()],
            animated_shape_ids=["42", "99"],
        )
        bld_lst = tree.find(f"{{{NS_P}}}bldLst")
        assert bld_lst is not None
        bld_ps = bld_lst.findall(f"{{{NS_P}}}bldP")
        assert len(bld_ps) == 2
        assert bld_ps[0].get("spid") == "42"
        assert bld_ps[1].get("spid") == "99"

    def test_no_bld_lst_when_empty(self):
        builder = AnimationXMLBuilder()
        ids = TimingIDAllocator().allocate(0)
        tree = builder.build_timing_tree(
            ids=ids,
            animation_elements=[],
            animated_shape_ids=[],
        )
        assert tree.find(f"{{{NS_P}}}bldLst") is None

    def test_zero_animations(self):
        builder = AnimationXMLBuilder()
        ids = TimingIDAllocator().allocate(0)
        tree = builder.build_timing_tree(
            ids=ids,
            animation_elements=[],
            animated_shape_ids=[],
        )
        # Structure should still be valid with empty click group
        click_ctn = tree.find(f".//{{{NS_P}}}cTn[@id='3']")
        assert click_ctn is not None


class TestBuildParContainerElem:
    """Test build_par_container_elem."""

    def test_returns_element(self):
        builder = AnimationXMLBuilder()
        from svg2ooxml.drawingml.xml_builder import p_elem as _p
        child = _p("set")

        par = builder.build_par_container_elem(
            par_id=4,
            duration_ms=1000,
            delay_ms=0,
            child_element=child,
        )
        assert isinstance(par, etree._Element)
        assert par.tag == f"{{{NS_P}}}par"

    def test_ctn_attributes(self):
        builder = AnimationXMLBuilder()
        from svg2ooxml.drawingml.xml_builder import p_elem as _p
        child = _p("set")

        par = builder.build_par_container_elem(
            par_id=4,
            duration_ms=1500,
            delay_ms=500,
            child_element=child,
            preset_id=10,
            preset_class="emph",
            preset_subtype=2,
        )
        ctn = par.find(f"{{{NS_P}}}cTn")
        assert ctn.get("id") == "4"
        assert ctn.get("dur") == "1500"
        assert ctn.get("fill") == "hold"
        assert ctn.get("presetID") == "10"
        assert ctn.get("presetClass") == "emph"
        assert ctn.get("presetSubtype") == "2"

    def test_start_condition(self):
        builder = AnimationXMLBuilder()
        from svg2ooxml.drawingml.xml_builder import p_elem as _p

        par = builder.build_par_container_elem(
            par_id=4,
            duration_ms=1000,
            delay_ms=250,
            child_element=_p("set"),
        )
        cond = par.find(f".//{{{NS_P}}}cond")
        assert cond is not None
        assert cond.get("delay") == "250"

    def test_child_appended(self):
        builder = AnimationXMLBuilder()
        from svg2ooxml.drawingml.xml_builder import p_elem as _p
        child = _p("set")

        par = builder.build_par_container_elem(
            par_id=4,
            duration_ms=1000,
            delay_ms=0,
            child_element=child,
        )
        child_tn_lst = par.find(f".//{{{NS_P}}}childTnLst")
        assert len(child_tn_lst) == 1
        assert child_tn_lst[0].tag == f"{{{NS_P}}}set"


class TestBuildBehaviorCoreElem:
    """Test build_behavior_core_elem."""

    def test_returns_element(self):
        builder = AnimationXMLBuilder()
        elem = builder.build_behavior_core_elem(
            behavior_id=5,
            duration_ms=1000,
            target_shape="shape1",
        )
        assert isinstance(elem, etree._Element)
        assert elem.tag == f"{{{NS_P}}}cBhvr"

    def test_ctn_attributes(self):
        builder = AnimationXMLBuilder()
        elem = builder.build_behavior_core_elem(
            behavior_id=5,
            duration_ms=2000,
            target_shape="shape1",
        )
        ctn = elem.find(f"{{{NS_P}}}cTn")
        assert ctn.get("id") == "5"
        assert ctn.get("dur") == "2000"
        assert ctn.get("fill") == "hold"

    def test_target_shape(self):
        builder = AnimationXMLBuilder()
        elem = builder.build_behavior_core_elem(
            behavior_id=5,
            duration_ms=1000,
            target_shape="shape42",
        )
        sp_tgt = elem.find(f".//{{{NS_P}}}spTgt")
        assert sp_tgt is not None
        assert sp_tgt.get("spid") == "shape42"

    def test_accel_decel(self):
        builder = AnimationXMLBuilder()
        elem = builder.build_behavior_core_elem(
            behavior_id=5,
            duration_ms=1000,
            target_shape="shape1",
            accel=50000,
            decel=50000,
        )
        ctn = elem.find(f"{{{NS_P}}}cTn")
        assert ctn.get("accel") == "50000"
        assert ctn.get("decel") == "50000"

    def test_attr_name_list(self):
        builder = AnimationXMLBuilder()
        elem = builder.build_behavior_core_elem(
            behavior_id=5,
            duration_ms=1000,
            target_shape="shape1",
            attr_name_list=["ppt_x", "ppt_y"],
        )
        attr_lst = elem.find(f"{{{NS_P}}}attrNameLst")
        assert attr_lst is not None
        names = attr_lst.findall(f"{{{NS_P}}}attrName")
        assert len(names) == 2

    def test_additive_sum(self):
        builder = AnimationXMLBuilder()
        elem = builder.build_behavior_core_elem(
            behavior_id=5,
            duration_ms=1000,
            target_shape="shape1",
            additive="sum",
        )
        assert elem.get("additive") == "sum"

    def test_additive_replace_omitted(self):
        """additive='replace' (SVG default) should not set attribute."""
        builder = AnimationXMLBuilder()
        elem = builder.build_behavior_core_elem(
            behavior_id=5,
            duration_ms=1000,
            target_shape="shape1",
            additive="replace",
        )
        assert elem.get("additive") is None

    def test_additive_none_omitted(self):
        """additive=None should not set attribute."""
        builder = AnimationXMLBuilder()
        elem = builder.build_behavior_core_elem(
            behavior_id=5,
            duration_ms=1000,
            target_shape="shape1",
        )
        assert elem.get("additive") is None

    def test_fill_mode_freeze_maps_to_hold(self):
        builder = AnimationXMLBuilder()
        elem = builder.build_behavior_core_elem(
            behavior_id=5,
            duration_ms=1000,
            target_shape="shape1",
            fill_mode="freeze",
        )
        ctn = elem.find(f"{{{NS_P}}}cTn")
        assert ctn.get("fill") == "hold"

    def test_fill_mode_remove(self):
        builder = AnimationXMLBuilder()
        elem = builder.build_behavior_core_elem(
            behavior_id=5,
            duration_ms=1000,
            target_shape="shape1",
            fill_mode="remove",
        )
        ctn = elem.find(f"{{{NS_P}}}cTn")
        assert ctn.get("fill") == "remove"

    def test_fill_mode_default_is_hold(self):
        builder = AnimationXMLBuilder()
        elem = builder.build_behavior_core_elem(
            behavior_id=5,
            duration_ms=1000,
            target_shape="shape1",
        )
        ctn = elem.find(f"{{{NS_P}}}cTn")
        assert ctn.get("fill") == "hold"

    def test_repeat_count_default(self):
        """Default repeat (None/1) → omit repeatCount (PPT default: play once)."""
        builder = AnimationXMLBuilder()
        elem = builder.build_behavior_core_elem(
            behavior_id=5,
            duration_ms=1000,
            target_shape="shape1",
        )
        ctn = elem.find(f"{{{NS_P}}}cTn")
        assert ctn.get("repeatCount") is None

    def test_repeat_count_indefinite(self):
        builder = AnimationXMLBuilder()
        elem = builder.build_behavior_core_elem(
            behavior_id=5,
            duration_ms=1000,
            target_shape="shape1",
            repeat_count="indefinite",
        )
        ctn = elem.find(f"{{{NS_P}}}cTn")
        assert ctn.get("repeatCount") == "indefinite"

    def test_repeat_count_integer(self):
        """repeat_count=3 → repeatCount='3000' (PPT uses millis)."""
        builder = AnimationXMLBuilder()
        elem = builder.build_behavior_core_elem(
            behavior_id=5,
            duration_ms=1000,
            target_shape="shape1",
            repeat_count=3,
        )
        ctn = elem.find(f"{{{NS_P}}}cTn")
        assert ctn.get("repeatCount") == "3000"

    def test_repeat_count_one_is_default(self):
        """repeat_count=1 → omit repeatCount (same as default)."""
        builder = AnimationXMLBuilder()
        elem = builder.build_behavior_core_elem(
            behavior_id=5,
            duration_ms=1000,
            target_shape="shape1",
            repeat_count=1,
        )
        ctn = elem.find(f"{{{NS_P}}}cTn")
        assert ctn.get("repeatCount") is None
