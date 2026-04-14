"""Tests for the animation oracle loader and SSOT invariants."""

from __future__ import annotations

import json
import re

import pytest
from lxml import etree

from svg2ooxml.drawingml.animation.oracle import (
    AnimationOracle,
    BehaviorFragment,
    FilterEntry,
    OracleSlotError,
    default_oracle,
)
from svg2ooxml.drawingml.xml_builder import NS_P


def test_default_oracle_loads_all_slots() -> None:
    oracle = default_oracle()
    slots = {slot.name for slot in oracle.slots()}
    expected = {
        "entr/fade",
        "entr/appear",
        "exit/fade",
        "emph/color",
        "emph/rotate",
        "emph/scale",
        "path/motion",
    }
    assert expected.issubset(slots)


def test_instantiate_fade_in_produces_click_effect_par() -> None:
    oracle = default_oracle()
    par = oracle.instantiate(
        "entr/fade",
        shape_id="2",
        par_id=6,
        duration_ms=1500,
        delay_ms=0,
        SET_BEHAVIOR_ID=7,
        EFFECT_BEHAVIOR_ID=71,
    )
    assert par.tag == f"{{{NS_P}}}par"
    ctn = par.find(f"{{{NS_P}}}cTn")
    assert ctn is not None
    assert ctn.get("nodeType") == "clickEffect"
    assert ctn.get("presetClass") == "entr"
    assert ctn.get("presetID") == "9"
    assert ctn.get("presetSubtype") == "0"
    assert ctn.get("dur") == "1500"
    assert ctn.get("grpId") == "6"
    children = ctn.find(f"{{{NS_P}}}childTnLst")
    assert children is not None
    tags = [c.tag for c in children]
    assert tags == [f"{{{NS_P}}}set", f"{{{NS_P}}}animEffect"]
    anim_effect = children.find(f"{{{NS_P}}}animEffect")
    assert anim_effect.get("transition") == "in"
    assert anim_effect.get("filter") == "fade"


def test_instantiate_requires_all_declared_tokens() -> None:
    oracle = default_oracle()
    with pytest.raises(ValueError, match="EFFECT_BEHAVIOR_ID"):
        oracle.instantiate(
            "entr/fade",
            shape_id="2",
            par_id=6,
            duration_ms=1500,
            delay_ms=0,
            SET_BEHAVIOR_ID=7,
        )


def test_instantiate_rejects_unknown_token() -> None:
    oracle = default_oracle()
    with pytest.raises(ValueError, match="EXTRA_TOKEN"):
        oracle.instantiate(
            "emph/rotate",
            shape_id="3",
            par_id=10,
            duration_ms=1000,
            delay_ms=0,
            BEHAVIOR_ID=11,
            ROTATION_BY="5400000",
            INNER_FILL="remove",
            EXTRA_TOKEN="nope",
        )


def test_missing_slot_raises() -> None:
    oracle = default_oracle()
    with pytest.raises(OracleSlotError):
        oracle.slot("nonexistent/slot")


def test_instantiate_motion_requires_path_data() -> None:
    oracle = default_oracle()
    with pytest.raises(ValueError, match="PATH_DATA"):
        oracle.instantiate(
            "path/motion",
            shape_id="1",
            par_id=4,
            duration_ms=1000,
            delay_ms=0,
            BEHAVIOR_ID=5,
        )
    par = oracle.instantiate(
        "path/motion",
        shape_id="1",
        par_id=4,
        duration_ms=1000,
        delay_ms=0,
        BEHAVIOR_ID=5,
        PATH_DATA="M 0 0 L 0.25 0 E",
        NODE_TYPE="clickEffect",
        INNER_FILL="remove",
    )
    anim_motion = par.find(f".//{{{NS_P}}}animMotion")
    assert anim_motion is not None
    assert anim_motion.get("path") == "M 0 0 L 0.25 0 E"


def test_emph_color_substitutes_srgb_values() -> None:
    oracle = default_oracle()
    par = oracle.instantiate(
        "emph/color",
        shape_id="12",
        par_id=20,
        duration_ms=500,
        delay_ms=0,
        BEHAVIOR_ID=21,
        FROM_COLOR="112233",
        TO_COLOR="AABBCC",
        TARGET_ATTRIBUTE="fill.color",
        INNER_FILL="remove",
    )
    xml = etree.tostring(par, encoding="unicode")
    assert 'val="112233"' in xml
    assert 'val="AABBCC"' in xml
    assert ">fill.color<" in xml


@pytest.mark.parametrize("slot_name", sorted({
    "entr/fade",
    "entr/appear",
    "exit/fade",
    "emph/color",
    "emph/rotate",
    "emph/scale",
    "path/motion",
}))
def test_template_tokens_declared_in_index(slot_name: str) -> None:
    """Every {TOKEN} in a template file must be declared in index.json."""
    oracle = default_oracle()
    slot = oracle.slot(slot_name)
    text = oracle.template_text(slot_name)
    found_tokens = set(re.findall(r"\{([A-Z_]+)\}", text))
    structural = {"SHAPE_ID", "PAR_ID", "DURATION_MS", "DELAY_MS"}
    declared = structural | set(slot.behavior_tokens) | set(slot.content_tokens)
    extras = found_tokens - declared
    assert not extras, (
        f"Slot {slot_name} template uses undeclared tokens: {sorted(extras)}"
    )
    unused = declared - found_tokens - structural
    assert not unused, (
        f"Slot {slot_name} declares tokens not found in template: {sorted(unused)}"
    )


def test_family_signature_class_matches_preset_class() -> None:
    oracle = default_oracle()
    for slot in oracle.slots():
        first_token = slot.family_signature.split("|")[1]
        assert first_token == slot.preset_class, (
            f"Slot {slot.name} family_signature preset_class '{first_token}' "
            f"does not match slot.preset_class '{slot.preset_class}'"
        )


def test_fresh_oracle_instance_reads_same_data(tmp_path) -> None:
    oracle_default = default_oracle()
    oracle_explicit = AnimationOracle(root=oracle_default.root)
    assert len(oracle_explicit.slots()) == len(oracle_default.slots())
    assert {s.name for s in oracle_explicit.slots()} == {
        s.name for s in oracle_default.slots()
    }


# ---------------------------------------------------------- compound slot


def test_compound_slot_is_registered() -> None:
    oracle = default_oracle()
    compound = oracle.slot("emph/compound")
    assert compound.preset_class == "emph"
    assert compound.preset_id is None
    assert compound.verification == "visually-verified"


def test_instantiate_compound_with_empty_behaviors() -> None:
    oracle = default_oracle()
    par = oracle.instantiate_compound(
        shape_id="2",
        par_id=5,
        duration_ms=3000,
        delay_ms=0,
        behaviors=[],
    )
    assert par.tag == f"{{{NS_P}}}par"
    ctn = par.find(f"{{{NS_P}}}cTn")
    assert ctn is not None
    assert ctn.get("nodeType") == "clickEffect"
    assert ctn.get("dur") == "3000"
    assert ctn.get("grpId") == "5"
    child_tn_lst = ctn.find(f"{{{NS_P}}}childTnLst")
    assert child_tn_lst is not None
    assert len(child_tn_lst) == 0


def test_instantiate_compound_stacks_heterogeneous_behaviors() -> None:
    oracle = default_oracle()
    par = oracle.instantiate_compound(
        shape_id="2",
        par_id=5,
        duration_ms=3000,
        delay_ms=0,
        behaviors=[
            BehaviorFragment("transparency", {
                "SET_BEHAVIOR_ID": 10,
                "EFFECT_BEHAVIOR_ID": 11,
                "TARGET_OPACITY": "0.5",
            }),
            BehaviorFragment("rotate", {
                "BEHAVIOR_ID": 20,
                "ROTATION_BY": "21600000",
            }),
            BehaviorFragment("scale", {
                "BEHAVIOR_ID": 30,
                "BY_X": "150000",
                "BY_Y": "150000",
            }),
            BehaviorFragment("motion", {
                "BEHAVIOR_ID": 40,
                "PATH_DATA": "M 0 0 L 0.1 0.1 E",
            }),
        ],
    )
    child_tn_lst = par.find(f"{{{NS_P}}}cTn/{{{NS_P}}}childTnLst")
    assert child_tn_lst is not None
    # transparency = 2 children, rotate = 1, scale = 1, motion = 1 → 5
    assert len(child_tn_lst) == 5
    tags = [etree.QName(c).localname for c in child_tn_lst]
    assert tags == ["set", "animEffect", "animRot", "animScale", "animMotion"]


def test_compound_fragment_token_substitution() -> None:
    oracle = default_oracle()
    par = oracle.instantiate_compound(
        shape_id="99",
        par_id=5,
        duration_ms=2500,
        behaviors=[
            BehaviorFragment("rotate", {
                "BEHAVIOR_ID": 60,
                "ROTATION_BY": "43200000",
            }),
        ],
    )
    anim_rot = par.find(f".//{{{NS_P}}}animRot")
    assert anim_rot is not None
    assert anim_rot.get("by") == "43200000"
    inner_ctn = anim_rot.find(f"{{{NS_P}}}cBhvr/{{{NS_P}}}cTn")
    assert inner_ctn is not None
    assert inner_ctn.get("id") == "60"
    assert inner_ctn.get("dur") == "2500"
    spt = anim_rot.find(f".//{{{NS_P}}}spTgt")
    assert spt is not None
    assert spt.get("spid") == "99"


def test_compound_accepts_plain_tuple_behaviors() -> None:
    oracle = default_oracle()
    par = oracle.instantiate_compound(
        shape_id="2",
        par_id=5,
        duration_ms=1000,
        behaviors=[
            ("bold", {"BEHAVIOR_ID": 10}),
            ("underline", {"BEHAVIOR_ID": 20}),
        ],
    )
    child_tn_lst = par.find(f"{{{NS_P}}}cTn/{{{NS_P}}}childTnLst")
    assert child_tn_lst is not None
    assert len(child_tn_lst) == 2


def test_compound_unknown_fragment_raises() -> None:
    oracle = default_oracle()
    with pytest.raises(OracleSlotError):
        oracle.instantiate_compound(
            shape_id="2",
            par_id=5,
            duration_ms=1000,
            behaviors=[BehaviorFragment("does_not_exist", {})],
        )


# ---------------------------------------------------------- filter vocabulary


def test_filter_vocabulary_loads_and_is_cached() -> None:
    oracle = default_oracle()
    vocab1 = oracle.filter_vocabulary()
    vocab2 = oracle.filter_vocabulary()
    assert vocab1 is vocab2  # cached tuple
    assert len(vocab1) > 0
    assert all(isinstance(e, FilterEntry) for e in vocab1)


def test_filter_vocabulary_core_values_present() -> None:
    """The empirically-verified filters must appear in the SSOT."""
    oracle = default_oracle()
    values = {e.value for e in oracle.filter_vocabulary()}
    core = {
        "fade", "dissolve",
        "wipe(down)", "wipe(up)", "wipe(left)", "wipe(right)",
        "wedge", "wheel(1)", "wheel(2)",
        "circle(in)", "circle(out)",
        "strips(downLeft)",
        "blinds(horizontal)",
        "checkerboard(across)",
        "barn(inVertical)",
        "randombar(horizontal)",
    }
    assert core.issubset(values)


def test_filter_vocabulary_verified_count_matches_sweep() -> None:
    """16 filters were empirically swept; at least 16 must carry visually-verified."""
    oracle = default_oracle()
    verified = [e for e in oracle.filter_vocabulary() if e.verification == "visually-verified"]
    # 16 swept entrance filters + image (pseudo, verified via transparency slot)
    assert len(verified) >= 16


def test_filter_entry_lookup_by_value() -> None:
    oracle = default_oracle()
    entry = oracle.filter_entry("wipe(down)")
    assert entry.value == "wipe(down)"
    assert entry.entrance_preset_id == 22
    assert entry.entrance_preset_subtype == 4
    assert entry.verification == "visually-verified"


def test_filter_entry_unknown_raises() -> None:
    oracle = default_oracle()
    with pytest.raises(OracleSlotError):
        oracle.filter_entry("nonexistent_filter_xyz")


def test_image_filter_is_pseudo() -> None:
    """The 'image' filter is a standalone animEffect value that PPT only honors
    inside emphasis effects (preset 9 transparency, preset 27 color pulse).
    Its preset-id sentinel is -1 to mark it as pseudo."""
    oracle = default_oracle()
    entry = oracle.filter_entry("image")
    assert entry.is_pseudo is True
    assert entry.verification == "visually-verified"


def test_filter_vocabulary_preset_subtype_mappings_consistent() -> None:
    """Entrance and exit preset mappings for directional filters should share
    the same preset_id (direction is carried by the filter string itself,
    not by changing the preset)."""
    oracle = default_oracle()
    wipe_down = oracle.filter_entry("wipe(down)")
    wipe_up = oracle.filter_entry("wipe(up)")
    # Both are preset 22, different subtypes
    assert wipe_down.entrance_preset_id == wipe_up.entrance_preset_id == 22
    assert wipe_down.entrance_preset_subtype != wipe_up.entrance_preset_subtype
