from __future__ import annotations

import zipfile
from itertools import count

from lxml import etree as ET
from tools.visual.powerpoint_oracle_starter_deck import (
    BuildEntry,
    InteractiveSequence,
    StartCondition,
    _build_anim_scale,
    _build_effect_par,
    _build_set_visibility,
    _build_timing_xml,
    build_oracle_starter_deck,
)

NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}


def test_build_timing_xml_includes_main_and_interactive_sequences() -> None:
    id_counter = count(40)
    main_effect = _build_effect_par(
        id_counter=id_counter,
        duration_ms=1,
        node_type="clickEffect",
        preset_id=1,
        preset_class="entr",
        grp_id=1,
        child_elements=[
            _build_set_visibility(
                id_counter=id_counter,
                target_shape_id=7,
                visibility="visible",
            )
        ],
    )
    interactive_effect = _build_effect_par(
        id_counter=id_counter,
        duration_ms=1500,
        node_type="clickEffect",
        preset_id=6,
        preset_class="emph",
        child_elements=[
            _build_anim_scale(
                id_counter=id_counter,
                target_shape_id=9,
                duration_ms=1500,
                by_x=150000,
                by_y=150000,
            )
        ],
    )

    timing_xml = _build_timing_xml(
        start_id=20,
        main_effect_pars=[main_effect],
        interactive_sequences=[
            InteractiveSequence(
                trigger_shape_ids=(7,),
                effect_pars=(interactive_effect,),
            )
        ],
        build_entries=[
            BuildEntry(shape_id=7, grp_id=1),
            BuildEntry(shape_id=9, grp_id=0),
        ],
    )

    root = ET.fromstring(timing_xml.encode("utf-8"))
    assert root.xpath("count(.//p:cTn[@nodeType='mainSeq'])", namespaces=NS) == 1.0
    assert root.xpath("count(.//p:cTn[@nodeType='interactiveSeq'])", namespaces=NS) == 1.0
    assert root.xpath("count(.//p:bldP)", namespaces=NS) == 2.0


def test_build_timing_xml_preserves_multiple_click_triggers() -> None:
    id_counter = count(100)
    pulse = _build_effect_par(
        id_counter=id_counter,
        duration_ms=1200,
        node_type="clickEffect",
        preset_id=6,
        preset_class="emph",
        child_elements=[
            _build_anim_scale(
                id_counter=id_counter,
                target_shape_id=11,
                duration_ms=1200,
                by_x=120000,
                by_y=120000,
            )
        ],
        start_conditions=[StartCondition(delay_ms=0)],
    )
    timing_xml = _build_timing_xml(
        start_id=60,
        interactive_sequences=[
            InteractiveSequence(
                trigger_shape_ids=(3, 4),
                effect_pars=(pulse,),
            )
        ],
    )

    root = ET.fromstring(timing_xml.encode("utf-8"))
    assert (
        root.xpath(
            "count(.//p:cTn[@nodeType='interactiveSeq']/p:stCondLst/p:cond[@evt='onClick'])",
            namespaces=NS,
        )
        == 2.0
    )
    assert (
        root.xpath(
            "count(.//p:seq[p:cTn[@nodeType='interactiveSeq']]/p:nextCondLst/p:cond[@evt='onClick'])",
            namespaces=NS,
        )
        == 2.0
    )


def test_oracle_starter_deck_includes_native_width_scale_semantics(tmp_path) -> None:
    deck_path = build_oracle_starter_deck(tmp_path / "oracle.pptx")

    with zipfile.ZipFile(deck_path) as pptx:
        slide_xml = pptx.read("ppt/slides/slide12.xml").decode("utf-8")

    root = ET.fromstring(slide_xml.encode("utf-8"))
    by_values = [
        (node.get("x"), node.get("y"))
        for node in root.xpath(".//p:animScale/p:by", namespaces=NS)
    ]
    assert ("33333", "100000") in by_values
    assert ("-66667", "0") in by_values
    assert ("85000", "100000") in by_values
    assert ("70588", "100000") in by_values
    assert ("16667", "100000") in by_values
    assert root.xpath("count(.//p:bldP[@animBg='1'])", namespaces=NS) == 5.0
