from __future__ import annotations

from lxml import etree as ET
from tools.ppt_research.powerpoint_motion_lab import (
    MotionLabCase,
    PlacedMotionLabCase,
    _build_case_par,
    _build_lab_timing,
    _patch_slide_xml_with_timing,
    _relative_motion_path,
)

from svg2ooxml.drawingml.animation.xml_builders import AnimationXMLBuilder
from svg2ooxml.drawingml.xml_builder import NS_P


def test_relative_motion_path_uses_slide_fractions() -> None:
    path = _relative_motion_path(
        dx_in=1.0,
        dy_in=0.5,
        slide_width_emu=12192000,
        slide_height_emu=6858000,
    )

    assert path == "M 0 0 L 0.075 0.0666667 E"


def test_build_case_par_rotation_only_emits_anim_rot() -> None:
    xml_builder = AnimationXMLBuilder()
    case = PlacedMotionLabCase(
        case=MotionLabCase("rot", "Rot only", initial_rotation_deg=-90.0),
        triangle_shape_id=7,
    )
    par = _build_case_par(
        xml_builder=xml_builder,
        placed_case=case,
        par_id=100,
        behavior_id=101,
        id_counter=iter(range(200, 260)),
        slide_size=(12192000, 6858000),
    )

    assert par.find(f".//{{{NS_P}}}animRot") is not None
    assert par.find(f".//{{{NS_P}}}animMotion") is None


def test_build_case_par_motion_first_preserves_child_order() -> None:
    xml_builder = AnimationXMLBuilder()
    case = PlacedMotionLabCase(
        case=MotionLabCase(
            "combo",
            "Combo",
            motion_dx_in=1.0,
            initial_rotation_deg=90.0,
            child_order="motion-first",
        ),
        triangle_shape_id=9,
    )
    par = _build_case_par(
        xml_builder=xml_builder,
        placed_case=case,
        par_id=100,
        behavior_id=101,
        id_counter=iter(range(200, 260)),
        slide_size=(12192000, 6858000),
    )

    child_tn_lst = par.find(f".//{{{NS_P}}}cTn/{{{NS_P}}}childTnLst")
    assert child_tn_lst[0].tag == f"{{{NS_P}}}animMotion"
    assert child_tn_lst[1].tag == f"{{{NS_P}}}par"


def test_build_case_par_rotation_first_swaps_child_order() -> None:
    xml_builder = AnimationXMLBuilder()
    case = PlacedMotionLabCase(
        case=MotionLabCase(
            "combo",
            "Combo",
            motion_dx_in=1.0,
            initial_rotation_deg=90.0,
            child_order="rotation-first",
        ),
        triangle_shape_id=9,
    )
    par = _build_case_par(
        xml_builder=xml_builder,
        placed_case=case,
        par_id=100,
        behavior_id=101,
        id_counter=iter(range(200, 260)),
        slide_size=(12192000, 6858000),
    )

    child_tn_lst = par.find(f".//{{{NS_P}}}cTn/{{{NS_P}}}childTnLst")
    assert child_tn_lst[0].tag == f"{{{NS_P}}}par"
    assert child_tn_lst[1].tag == f"{{{NS_P}}}animMotion"


def test_build_lab_timing_emits_one_effect_group_per_case() -> None:
    timing_xml = _build_lab_timing(
        [
            PlacedMotionLabCase(
                case=MotionLabCase("a", "A", initial_rotation_deg=-90.0),
                triangle_shape_id=5,
            ),
            PlacedMotionLabCase(
                case=MotionLabCase("b", "B", motion_dx_in=1.0, initial_rotation_deg=90.0),
                triangle_shape_id=6,
            ),
        ],
        start_id=10,
        slide_size=(12192000, 6858000),
    )

    root = ET.fromstring(timing_xml.encode("utf-8"))
    assert root.tag == f"{{{NS_P}}}timing"
    assert len(root.findall(f".//{{{NS_P}}}bldP")) == 4


def test_patch_slide_xml_with_timing_appends_timing_node() -> None:
    slide_xml = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        b"<p:cSld/></p:sld>"
    )
    timing_xml = '<p:timing xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>'

    patched = _patch_slide_xml_with_timing(slide_xml, timing_xml)
    root = ET.fromstring(patched)

    assert root.find(f"{{{NS_P}}}timing") is not None
