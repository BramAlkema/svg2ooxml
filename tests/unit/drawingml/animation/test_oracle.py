"""Tests for the animation oracle loader and SSOT invariants."""

from __future__ import annotations

import json
import re

import pytest
from lxml import etree

from svg2ooxml.drawingml.animation.oracle import (
    AnimationOracle,
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
